import logging
import uuid

from app.config import get_settings
from app.db import get_db_session
from app.errors import AppException
from app.models import Artifact, utc_now
from app.schemas import ArtifactCreate, ArtifactResponse
from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/artifacts", tags=["artifacts"])
logger = logging.getLogger(__name__)
settings = get_settings()

VALID_ARTIFACT_TYPES = {"markdown", "html"}


@router.post("", response_model=ArtifactResponse, status_code=status.HTTP_201_CREATED)
async def create_artifact_endpoint(
    body: ArtifactCreate,
    db: AsyncSession = Depends(get_db_session),
) -> ArtifactResponse:
    """Create and persist an artifact with size and type validation."""
    clean_type = body.type.strip().lower()
    if clean_type not in VALID_ARTIFACT_TYPES:
        raise AppException(
            code="invalid_artifact_type",
            message=f"Artifact type must be one of {sorted(list(VALID_ARTIFACT_TYPES))}, got '{body.type}'",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    content_bytes = len(body.content.encode("utf-8"))
    if content_bytes > settings.artifact_max_bytes:
        raise AppException(
            code="artifact_too_large",
            message=f"Artifact size ({content_bytes} bytes) exceeds limit of {settings.artifact_max_bytes} bytes",
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )

    artifact = Artifact(
        id=uuid.uuid4(),
        session_id=body.session_id,
        type=clean_type,
        title=body.title,
        content=body.content,
        created_at=utc_now(),
    )
    db.add(artifact)
    await db.commit()
    await db.refresh(artifact)
    logger.info("Artifact created: type=%s bytes=%d id=%s", clean_type, content_bytes, str(artifact.id))
    return ArtifactResponse.model_validate(artifact)


@router.get("/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(
    artifact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> ArtifactResponse:
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
    return ArtifactResponse.model_validate(artifact)
