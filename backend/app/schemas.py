"""Pydantic v2 schemas for request and response validation."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class MessageBase(BaseModel):
    role: str
    content: str
    intent: Optional[str] = None
    citations: List[Dict[str, Any]] = Field(default_factory=list)
    tool_trace: List[Dict[str, Any]] = Field(default_factory=list)
    degraded: bool = False
    latency_ms: Optional[int] = None
    warnings: List[str] = Field(default_factory=list)


class MessageResponse(MessageBase):
    id: uuid.UUID
    session_id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SessionCreate(BaseModel):
    title: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    client_id: Optional[str] = Field(None, max_length=256)
    user_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class SessionResponse(BaseModel):
    id: uuid.UUID
    title: Optional[str] = None
    client_id: Optional[str] = None
    user_metadata: Dict[str, Any] = Field(default_factory=dict)
    llm_provider: str
    llm_model: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SessionDetailResponse(SessionResponse):
    messages: List[MessageResponse] = Field(default_factory=list)


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)


class CitationItem(BaseModel):
    n: int
    chunk_id: uuid.UUID
    doc_slug: str
    title: str
    guest: Optional[str] = None
    passage: str


class ChatResponse(BaseModel):
    message: MessageResponse
    citations: List[CitationItem] = Field(default_factory=list)
    intent: Optional[str] = None
    degraded: bool = False
    latency_ms: Optional[int] = None
    artifact: Optional[Dict[str, Any]] = None
    warnings: List[str] = Field(default_factory=list)


class ArtifactCreate(BaseModel):
    session_id: uuid.UUID
    title: str = Field(..., min_length=1, max_length=200)
    type: str = Field(..., description="Artifact type: markdown or html")
    content: str = Field(..., description="Raw text or HTML content")


class ArtifactResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    message_id: Optional[uuid.UUID] = None
    type: str
    title: str
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

