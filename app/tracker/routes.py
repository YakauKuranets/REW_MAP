from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.realtime.broker import get_broker
from app.schemas import AgentLocationUpdate, TrackerResponse

router = APIRouter()


def publish_event_to_redis(channel: str, payload: dict) -> None:
    broker = get_broker()
    ok = broker.publish_event(channel, payload)
    if not ok:
        raise RuntimeError("failed to publish to redis")


@router.post("/update_location", response_model=TrackerResponse)
async def update_agent_location(
    payload: AgentLocationUpdate,
    background_tasks: BackgroundTasks,
):
    """Принимает координаты агента, валидирует и публикует в realtime-шину."""
    try:
        event_data = {
            "event": "AGENT_LOCATION_UPDATE",
            "data": payload.model_dump(),
        }
        background_tasks.add_task(publish_event_to_redis, "realtime_events", event_data)
        return TrackerResponse(
            status="success",
            message="Coordinates locked.",
            processed_id=payload.agent_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
