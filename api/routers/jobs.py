import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List

from ..database import get_db, Job, JobEvent, Agent, BillingTransaction
from ..models import JobCreate, JobResponse
from ..auth import verify_api_key_with_context
from ..scorer import compute_trace_score

router = APIRouter()

@router.post("/jobs", response_model=JobResponse)
async def post_job(
    job_data: JobCreate,
    auth_tuple: tuple = Depends(verify_api_key_with_context),
    db: AsyncSession = Depends(get_db)
):
    dev, api_key = auth_tuple
    
    if dev.balance_usdc < job_data.budget_usdc and not api_key.is_test:
        raise HTTPException(status_code=402, detail="Insufficient balance for job budget.")

    # Get eligible verified agents
    result = await db.execute(
        select(Agent).filter(
            Agent.status == "verified",
            Agent.pricing_usdc <= job_data.budget_usdc
        )
    )
    agents = result.scalars().all()
    # filter by capability loosely
    agents = [a for a in agents if job_data.task_type in a.capabilities or not a.capabilities]
    
    if not agents:
        raise HTTPException(status_code=404, detail="No eligible agents found.")

    best_agent = None
    best_score = -1.0
    
    for a in agents:
        try:
            score_res = await compute_trace_score(
                provider_id=a.id,
                job_capability=job_data.task_type,
                price_usdc=a.pricing_usdc,
                cohort_median_price=None,
                provider_capabilities=a.capabilities,
            )
            if score_res.routing_decision == "ROUTE" and score_res.score > best_score:
                best_score = score_res.score
                best_agent = a
        except Exception:
            continue

    if not best_agent:
        raise HTTPException(status_code=404, detail="No trusted agents available.")

    # Assign
    job_id = str(uuid.uuid4())
    job = Job(
        id=job_id,
        buyer_id=dev.id,
        task_type=job_data.task_type,
        budget_usdc=job_data.budget_usdc,
        status="assigned",
        assigned_agent_id=best_agent.id
    )
    db.add(job)
    
    # Charge buyer
    if not api_key.is_test:
        dev.balance_usdc -= job_data.budget_usdc
        txn = BillingTransaction(
            developer_id=dev.id,
            amount_usdc=-job_data.budget_usdc,
            balance_after=dev.balance_usdc,
            transaction_type="job_payment",
            endpoint="/v1/jobs"
        )
        db.add(txn)
        
    db.add(JobEvent(job_id=job_id, status_from="posted", status_to="assigned"))
    await db.commit()
    await db.refresh(job)
    return job

@router.get("/jobs", response_model=List[JobResponse])
async def list_jobs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Job).order_by(Job.created_at.desc()).limit(50))
    return result.scalars().all()

@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)):
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job

@router.post("/jobs/{job_id}/complete")
async def complete_job(
    job_id: str,
    success: bool,
    auth_tuple: tuple = Depends(verify_api_key_with_context),
    db: AsyncSession = Depends(get_db)
):
    dev, _ = auth_tuple
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
        
    agent = await db.get(Agent, job.assigned_agent_id)
    if agent.owner_developer_id != dev.id:
        raise HTTPException(403, "Only the assigned agent's owner can complete this job.")
        
    new_status = "completed" if success else "failed"
    db.add(JobEvent(job_id=job_id, status_from=job.status, status_to=new_status))
    job.status = new_status
    job.completed_at = datetime.now(timezone.utc)
    
    # Report to TRACE scoring engine. Shared with /v1/events and
    # /v1/webhooks/* via state_manager.apply_outcome so all call sites update
    # EMA/CUSUM state identically -- this endpoint used to reimplement the
    # same sequence by hand and had drifted out of sync (it discarded the
    # CUSUM "fired" signal the same way the events path used to).
    from ..state import state_manager

    await state_manager.add_trust_edge(job.buyer_id, agent.id)
    await state_manager.apply_outcome(agent.id, success)

    await db.commit()
    return {"status": "ok"}
