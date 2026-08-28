from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from datetime import datetime, timezone
from ..database import get_db, ReviewTask
from ..models import ReviewTaskResponse

router = APIRouter()

@router.get("/reviews", response_model=List[ReviewTaskResponse])
async def list_reviews(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ReviewTask).order_by(ReviewTask.created_at.desc()).limit(100))
    return result.scalars().all()

@router.post("/reviews/{task_id}/action")
async def resolve_review(task_id: int, action: str, db: AsyncSession = Depends(get_db)):
    task = await db.get(ReviewTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Review task not found")
    task.status = "RESOLVED"
    task.recommended_action = action
    task.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "ok"}
