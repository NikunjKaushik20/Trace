from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from ..database import get_db, BillingTransaction
from ..models import PaymentResponse

router = APIRouter()

@router.get("/payments", response_model=List[PaymentResponse])
async def list_payments(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(BillingTransaction).order_by(BillingTransaction.created_at.desc()).limit(100))
    return result.scalars().all()
