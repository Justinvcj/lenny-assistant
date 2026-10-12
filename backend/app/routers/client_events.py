"""Client events router for frontend telemetry and observability."""

import json
import logging

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/client-events", tags=["events"])
logger = logging.getLogger("client_events")


class ClientEventRequest(BaseModel):
    """Small structured client telemetry event (contains no sensitive user content)."""

    type: str = Field(..., min_length=1, max_length=128)
    artifact_id: str | None = Field(None, max_length=128)
    reason: str = Field(..., min_length=1, max_length=1024)


@router.post("", status_code=status.HTTP_204_NO_CONTENT)
async def record_client_event(event: ClientEventRequest) -> Response:
    """Record and log client diagnostic events as structured single-line JSON."""
    payload = {
        "event": "client_event",
        "type": event.type,
        "artifact_id": event.artifact_id,
        "reason": event.reason,
    }
    # Log as exactly one structured JSON line
    logger.info(json.dumps(payload))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
