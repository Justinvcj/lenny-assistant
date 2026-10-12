import json
import uuid

from app.config import get_settings
from app.db import get_db_session
from app.errors import AppException
from app.models import Session
from app.schemas import SessionCreate, SessionDetailResponse, SessionResponse
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

router = APIRouter(prefix="/sessions", tags=["sessions"])
settings = get_settings()

MAX_USER_METADATA_BYTES = 16384  # 16 KB maximum


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    request: Request,
    body: SessionCreate = SessionCreate(),
    db: AsyncSession = Depends(get_db_session),
) -> SessionResponse:
    raw_meta = body.user_metadata if body.user_metadata is not None else {}
    if not isinstance(raw_meta, dict):
        raise AppException(
            code="validation_error",
            message="user_metadata must be a JSON object",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    try:
        serialized_meta = json.dumps(raw_meta)
    except (TypeError, ValueError) as exc:
        raise AppException(
            code="validation_error",
            message=f"user_metadata is not JSON serializable: {exc}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    if len(serialized_meta.encode("utf-8")) > MAX_USER_METADATA_BYTES:
        raise AppException(
            code="validation_error",
            message=f"user_metadata exceeds maximum allowed size of {MAX_USER_METADATA_BYTES} bytes",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    meta = dict(raw_meta)

    # Capture request metadata per brief requirement (user-agent and Accept-Language; NEVER IP)
    user_agent = request.headers.get("user-agent")
    if user_agent:
        meta["user_agent"] = user_agent

    accept_language = request.headers.get("accept-language")
    if accept_language:
        meta["accept_language"] = accept_language

    session = Session(
        title=body.title,
        client_id=body.client_id,
        user_metadata=meta,
        llm_provider=body.llm_provider or settings.llm_provider,
        llm_model=body.llm_model or settings.llm_model,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return SessionResponse.model_validate(session)


@router.get("", response_model=list[SessionResponse])
async def list_sessions(
    db: AsyncSession = Depends(get_db_session),
) -> list[SessionResponse]:
    stmt = select(Session).order_by(Session.created_at.desc())
    result = await db.execute(stmt)
    sessions = result.scalars().all()
    return [SessionResponse.model_validate(s) for s in sessions]


@router.get("/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> SessionDetailResponse:
    stmt = (
        select(Session)
        .where(Session.id == session_id)
        .options(selectinload(Session.messages))
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if not session:
        raise AppException(
            code="session_not_found",
            message=f"Session {session_id} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return SessionDetailResponse.model_validate(session)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> None:
    stmt = select(Session).where(Session.id == session_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if not session:
        raise AppException(
            code="session_not_found",
            message=f"Session {session_id} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    await db.delete(session)
    await db.commit()
