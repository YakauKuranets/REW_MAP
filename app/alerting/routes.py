from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.schemas import ScanResponse

router = APIRouter()


class AlertEventPayload(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    severity: str = Field(default="info")
    source: str = Field(default="system")
    details: dict = Field(default_factory=dict)


@router.post("/emit", response_model=ScanResponse)
async def emit_alert(payload: AlertEventPayload):
    try:
        _ = payload.model_dump()
        return ScanResponse(status="accepted", task_id=None, message="Alert accepted")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
