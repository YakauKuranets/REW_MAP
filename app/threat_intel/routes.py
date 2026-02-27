from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas import ThreatIntelPayload
from app.threat_intel.attribution_engine import enrich_actor_profile

router = APIRouter()


@router.post("/analyze_actor")
async def analyze_threat_actor(payload: ThreatIntelPayload):
    if not payload.alias and not payload.email:
        raise HTTPException(status_code=400, detail="Alias or email must be provided")

    try:
        alias = payload.alias or payload.email or "unknown"
        profile = await enrich_actor_profile(alias=alias, email=payload.email)
        return {"status": "success", "profile": profile}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
