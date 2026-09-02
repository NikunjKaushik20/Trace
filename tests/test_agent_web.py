"""
Tests for the /agent HTTP surface (buildathon/agent/web.py), included by
the merchant app. The key-present path (an actual gpt-4o-mini run) is not
exercised here -- that needs network and is covered by
`python -m buildathon.demo.agent_demo`; the loop itself is unit-tested in
test_agent_buyer.py. These pin the config/gating behavior.

Run from the repo root:
    pytest buildathon/tests/test_agent_web.py -v
"""
import httpx
import pytest

from buildathon.merchant.app import app


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_agent_config_disabled_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    async with _client() as c:
        r = await c.get("/agent/config")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False
    assert body["model"] == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_agent_config_enabled_with_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    async with _client() as c:
        r = await c.get("/agent/config")
    assert r.status_code == 200
    assert r.json()["enabled"] is True


@pytest.mark.asyncio
async def test_agent_run_503_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    async with _client() as c:
        r = await c.post("/agent/run", json={"mode": "honest"})
    assert r.status_code == 503
    assert "OPENAI_API_KEY" in r.json()["detail"]


@pytest.mark.asyncio
async def test_agent_run_rejects_unknown_mode(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    async with _client() as c:
        r = await c.post("/agent/run", json={"mode": "banana"})
    assert r.status_code == 422  # pydantic Literal validation, before any run
