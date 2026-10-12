"""Pydantic v2 schemas for request and response validation."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MessageBase(BaseModel):
    role: str
    content: str
    intent: str | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    tool_trace: list[dict[str, Any]] = Field(default_factory=list)
    degraded: bool = False
    latency_ms: int | None = None
    warnings: list[str] = Field(default_factory=list)


class MessageResponse(MessageBase):
    id: uuid.UUID
    session_id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SessionCreate(BaseModel):
    title: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    client_id: str | None = Field(None, max_length=256)
    user_metadata: dict[str, Any] | None = Field(default_factory=dict)


class SessionResponse(BaseModel):
    id: uuid.UUID
    title: str | None = None
    client_id: str | None = None
    user_metadata: dict[str, Any] = Field(default_factory=dict)
    llm_provider: str
    llm_model: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SessionDetailResponse(SessionResponse):
    messages: list[MessageResponse] = Field(default_factory=list)


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)


class CitationItem(BaseModel):
    n: int
    chunk_id: uuid.UUID
    doc_slug: str
    title: str
    guest: str | None = None
    passage: str


class ChatResponse(BaseModel):
    message: MessageResponse
    citations: list[CitationItem] = Field(default_factory=list)
    intent: str | None = None
    degraded: bool = False
    latency_ms: int | None = None
    artifact: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)


class ArtifactCreate(BaseModel):
    session_id: uuid.UUID
    title: str = Field(..., min_length=1, max_length=200)
    type: str = Field(..., description="Artifact type: markdown or html")
    content: str = Field(..., description="Raw text or HTML content")


class ArtifactResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    message_id: uuid.UUID | None = None
    type: str
    title: str
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

