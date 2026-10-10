"""Artifacts router for fetching saved artifacts."""

import uuid
from typing import Any, Dict
from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.errors import AppException
from app.models import Artifact

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.get("/{artifact_id}")
async def get_artifact(
    artifact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Fetch an artifact by its UUID."""
    stmt = select(Artifact).where(Artifact.id == artifact_id)
    res = await db.execute(stmt)
    artifact = res.scalar_one_or_none()
    if not artifact:
        raise AppException(
            code="artifact_not_found",
            message=f"Artifact {artifact_id} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return {
        "id": str(artifact.id),
        "session_id": str(artifact.session_id),
        "message_id": str(artifact.message_id) if artifact.message_id else None,
        "type": artifact.type,
        "title": artifact.title,
        "content": artifact.content,
        "created_at": artifact.created_at.isoformat(),
    }
