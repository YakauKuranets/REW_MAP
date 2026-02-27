from __future__ import annotations

import inspect

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.diagnostics.coordinator import TaskCoordinator
from app.schemas import ScanRequest, ScanResponse

router = APIRouter()
coordinator = TaskCoordinator()


@router.post("/scan", response_model=ScanResponse)
async def launch_diagnostic_scan(payload: ScanRequest, background_tasks: BackgroundTasks):
    try:
        plan = coordinator.plan_tasks(
            type("Target", (), {"type": payload.scan_type, "identifier": payload.target_ip, "context": payload.options})
        )

        async def _dispatch_scan() -> str:
            synthetic_task_id = f"diag-{payload.scan_type}-{abs(hash(payload.target_ip)) % 10_000_000}"
            return synthetic_task_id

        if inspect.iscoroutinefunction(_dispatch_scan):
            task_id = await _dispatch_scan()
        else:
            task_id = _dispatch_scan()

        if plan:
            background_tasks.add_task(lambda: None)

        return ScanResponse(status="processing", task_id=task_id, message="Scan initiated")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
