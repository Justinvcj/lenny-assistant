"""Session CRUD endpoints."""

import uuid
from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db import get_db_session
from app.errors import AppException
from app.models import Session
from app.schemas import SessionCreate, SessionDetailResponse, SessionResponse

router = APIRouter(prefix="/sessions", tags=["sessions"])
settings = get_settings()


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: SessionCreate = SessionCreate(),
    db: AsyncSession = Depends(get_db_session),
) -> SessionResponse:
    session = Session(
        title=body.title,
        llm_provider=body.llm_provider or settings.llm_provider,
        llm_model=body.llm_model or settings.llm_model,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return SessionResponse.model_validate(session)


@router.get("", response_model=List[SessionResponse])
async def list_sessions(
    db: AsyncSession = Depends(get_db_session),
) -> List[SessionResponse]:
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
    return None
