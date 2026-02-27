from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas import ScanRequest, ScanResponse

router = APIRouter()


@router.post("/collect", response_model=ScanResponse)
async def launch_osint_collection(payload: ScanRequest):
    try:
        task_id = f"osint-{abs(hash((payload.target_ip, payload.scan_type))) % 10_000_000}"
        return ScanResponse(status="processing", task_id=task_id, message="OSINT collection initiated")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
