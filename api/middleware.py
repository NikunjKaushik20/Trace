"""
TRACE API — Structured Logging with Request IDs, Security Headers, and Request Timeout
"""

import asyncio
import logging
import uuid
import time
from contextvars import ContextVar
from typing import Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from pythonjsonlogger import jsonlogger

from .config import settings

# Context variable to store request ID across async calls
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses."""
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        # CSP: 'self' is appropriate for API-only responses.
        # If serving HTML/frontend through this API, loosen to allow scripts/styles as needed.
        response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response


class RequestTimeoutMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce a maximum request processing time."""

    async def dispatch(self, request: Request, call_next):
        try:
            return await asyncio.wait_for(
                call_next(request),
                timeout=settings.request_timeout
            )
        except asyncio.TimeoutError:
            logger = logging.getLogger("trace.api")
            logger.error(
                "Request timed out",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "timeout": settings.request_timeout,
                }
            )
            return Response(
                content='{"detail":"Request timed out"}',
                status_code=504,
                media_type="application/json"
            )


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware to add request ID to all requests and responses."""

    async def dispatch(self, request: Request, call_next):
        # Generate or extract request ID
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        
        # Store in context variable for access in other parts of the code
        request_id_var.set(request_id)
        
        # Add to request state for access in route handlers
        request.state.request_id = request_id
        
        # Log request start
        logger = logging.getLogger("trace.api")
        logger.info(
            "Request started",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "client": request.client.host if request.client else None,
            }
        )
        
        start_time = time.perf_counter()
        
        try:
            response = await call_next(request)
            
            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id
            
            # Log request completion
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "Request completed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                }
            )
            
            return response
            
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "Request failed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "error": str(e),
                    "duration_ms": round(duration_ms, 2),
                },
                exc_info=True
            )
            raise


def get_request_id() -> Optional[str]:
    """Get the current request ID from context."""
    return request_id_var.get()


def setup_logging():
    """Configure structured JSON logging for the application."""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Remove existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        
    logHandler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    logHandler.setFormatter(formatter)
    logger.addHandler(logHandler)
    
    # Reduce noise from third-party libraries
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    
    # Set our app loggers to INFO
    logging.getLogger("trace.api").setLevel(logging.INFO)
    logging.getLogger("trace.state").setLevel(logging.INFO)
    logging.getLogger("trace.worker").setLevel(logging.INFO)
    logging.getLogger("trace.auth").setLevel(logging.INFO)