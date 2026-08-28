from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from ..database import get_db, RulePolicy
from ..models import RulePolicyResponse, RulePolicyCreate

router = APIRouter()

@router.get("/policies", response_model=List[RulePolicyResponse])
async def list_policies(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RulePolicy).order_by(RulePolicy.created_at.desc()))
    return result.scalars().all()

@router.post("/policies", response_model=RulePolicyResponse)
async def create_policy(policy: RulePolicyCreate, db: AsyncSession = Depends(get_db)):
    db_policy = RulePolicy(
        rule_type=policy.rule_type,
        condition=policy.condition,
        action=policy.action
    )
    db.add(db_policy)
    await db.commit()
    await db.refresh(db_policy)
    return db_policy
