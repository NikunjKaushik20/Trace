import uuid
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List

from ..database import get_db, Agent
from ..models import AgentCreate, AgentResponse
from ..auth import verify_api_key_with_context

router = APIRouter()

@router.post("/agents", response_model=AgentResponse)
async def register_agent(
    agent_data: AgentCreate,
    auth_tuple: tuple = Depends(verify_api_key_with_context),
    db: AsyncSession = Depends(get_db)
):
    dev, _ = auth_tuple
    agent_id = str(uuid.uuid4())
    status = "pending"
    
    # ponytail: lightweight challenge ping
    challenge = str(uuid.uuid4())
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.post(agent_data.endpoint_url, json={"challenge": challenge})
            if resp.status_code == 200 and resp.json().get("response") == challenge:
                status = "verified"
    except Exception:
        pass # stays pending
        
    new_agent = Agent(
        id=agent_id,
        owner_developer_id=dev.id,
        name=agent_data.name,
        description=agent_data.description,
        capabilities=agent_data.capabilities,
        endpoint_url=agent_data.endpoint_url,
        wallet_address=agent_data.wallet_address,
        lightning_address=agent_data.lightning_address,
        pricing_usdc=agent_data.pricing_usdc,
        status=status,
    )
    db.add(new_agent)
    await db.commit()
    await db.refresh(new_agent)
    return new_agent

@router.get("/agents", response_model=List[AgentResponse])
async def list_agents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Agent).filter(Agent.status == "verified"))
    return result.scalars().all()
