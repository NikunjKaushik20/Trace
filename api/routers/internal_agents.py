from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class ChallengeReq(BaseModel):
    challenge: str

@router.post("/summarize")
async def summarize(req: dict):
    if "challenge" in req:
        return {"response": req["challenge"]}
    return {"result": "Summarized text"}

@router.post("/translate")
async def translate(req: dict):
    if "challenge" in req:
        return {"response": req["challenge"]}
    return {"result": "Translated text"}

@router.post("/price-lookup")
async def price_lookup(req: dict):
    if "challenge" in req:
        return {"response": req["challenge"]}
    return {"result": "42.00"}
