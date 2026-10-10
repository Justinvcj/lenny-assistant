"""Chat router handling message submission, retrieval grounding, agent execution, and citation verification.

Endpoints:
    POST /sessions/{session_id}/messages
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.orchestrator import run_agent
from app.agent.prompts import EXACT_REFUSAL_MESSAGE, build_system_prompt, rewrite_query
from app.agent.router import Intent, classify_intent
from app.agent.verify import verify_citations
from app.config import get_settings
from app.db import get_db_session
from app.errors import AppException
from app.llm.base import LLMProvider
from app.llm.factory import get_provider
from app.models import Artifact, Message, Session, utc_now
from app.rag.embeddings import get_embeddings_client
from app.rag.retrieval import retrieve
from app.schemas import ChatResponse, CitationItem, MessageCreate, MessageResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["chat"])


# ---------------------------------------------------------------------------
# Dependency providers (can be overridden via app.dependency_overrides)
# ---------------------------------------------------------------------------


def get_chat_provider() -> LLMProvider:
    """Return the active LLM provider."""
    return get_provider()


def get_chat_embedder() -> Any:
    """Return the active embeddings client."""
    return get_embeddings_client()


# ---------------------------------------------------------------------------
# POST /sessions/{session_id}/messages
# ---------------------------------------------------------------------------


@router.post("/{session_id}/messages", response_model=ChatResponse)
async def post_message(
    session_id: uuid.UUID,
    body: MessageCreate,
    db: AsyncSession = Depends(get_db_session),
    provider: LLMProvider = Depends(get_chat_provider),
    embedder: Any = Depends(get_chat_embedder),
) -> ChatResponse:
    """Send a message to a session, run RAG retrieval + agent, and persist response.

    Pipeline:
      1. Validate session existence (404 if missing).
      2. Persist user message.
      3. Fetch prior conversation history.
      4. Classify intent (QA, ESSAY, ARTIFACT).
      5. Rewrite query for dense semantic retrieval.
      6. Retrieve candidate chunks with cosine similarity.
      7. IMMEDIATE REFUSAL if top score < RETRIEVAL_MIN_SCORE (zero LLM calls).
      8. Build grounded prompt with numbered <source> blocks.
      9. Call agent orchestrator.
      10. Verify citations; retry once if non-refusal has zero citations.
      11. Persist assistant message + optional artifact.
      12. Return ChatResponse.
    """
    settings = get_settings()
    t0 = time.perf_counter()

    # 1. Validate session existence
    stmt = select(Session).where(Session.id == session_id)
    res = await db.execute(stmt)
    session_obj = res.scalar_one_or_none()
    if not session_obj:
        raise AppException(
            code="session_not_found",
            message=f"Session {session_id} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    # 2. Persist user message
    user_msg = Message(
        id=uuid.uuid4(),
        session_id=session_id,
        role="user",
        content=body.content.strip(),
        created_at=utc_now(),
    )
    db.add(user_msg)
    await db.commit()
    await db.refresh(user_msg)

    # 3. Fetch prior session history (excluding current user turn)
    history_stmt = (
        select(Message)
        .where(Message.session_id == session_id)
        .where(Message.id != user_msg.id)
        .order_by(Message.created_at.asc())
    )
    history_res = await db.execute(history_stmt)
    history_messages = list(history_res.scalars().all())

    # 4. Classify intent
    intent = classify_intent(body.content, history=history_messages)

    # 5. Rewrite query for follow-up context
    search_query = rewrite_query(body.content, history=history_messages)

    # 6. Retrieve candidate chunks
    threshold = settings.retrieval_min_score
    raw_chunks = await retrieve(
        query=search_query,
        db=db,
        top_k=settings.retrieval_top_k,
        min_score=None,
        embedder=embedder,
    )

    top_score = raw_chunks[0].score if raw_chunks else 0.0

    # 7. IMMEDIATE REFUSAL with ZERO LLM calls if top retrieval score < threshold
    if not raw_chunks or top_score < threshold:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "Immediate refusal triggered: top_score=%.4f < threshold=%.4f query=%r",
            top_score,
            threshold,
            search_query,
        )
        assistant_msg = Message(
            id=uuid.uuid4(),
            session_id=session_id,
            role="assistant",
            content=EXACT_REFUSAL_MESSAGE,
            intent=intent.value,
            citations=[],
            created_at=utc_now(),
            tool_trace=[
                {
                    "action": "refusal_below_retrieval_threshold",
                    "top_score": round(top_score, 4),
                    "threshold": threshold,
                    "chunks_found": len(raw_chunks),
                }
            ],
            degraded=False,
            latency_ms=elapsed_ms,
        )
        db.add(assistant_msg)
        await db.commit()
        await db.refresh(assistant_msg)

        return ChatResponse(
            message=MessageResponse.model_validate(assistant_msg),
            citations=[],
            intent=intent.value,
            degraded=False,
            latency_ms=elapsed_ms,
            artifact=None,
        )

    # Filter to chunks passing threshold
    sources = [c for c in raw_chunks if c.score >= threshold]

    # 8. Build grounded prompt
    system_prompt = build_system_prompt(
        sources=sources,
        history=history_messages,
        max_history_turns=settings.history_turns,
    )

    # 9. Call agent orchestrator
    agent_res = await run_agent(
        intent=intent,
        system_prompt=system_prompt,
        user_message=body.content,
        provider=provider,
        timeout_s=settings.agent_timeout_s,
    )

    # 10. Citation verification & retry protocol
    verif = verify_citations(answer=agent_res.content, sources=sources, db=db)

    tool_trace = list(agent_res.tool_trace)
    degraded = agent_res.degraded
    artifact_data = agent_res.artifact

    if verif.needs_retry and not verif.is_refusal:
        logger.info("Citation verification failed on first attempt — retrying once")
        retry_prompt = (
            f"{body.content}\n\n"
            "[Grounding reminder: You must tag every claim with its source identifier [S#] "
            "using ONLY the provided sources. If the sources do not contain the answer, "
            f"reply exactly: {EXACT_REFUSAL_MESSAGE}]"
        )
        retry_res = await run_agent(
            intent=intent,
            system_prompt=system_prompt,
            user_message=retry_prompt,
            provider=provider,
            timeout_s=settings.agent_timeout_s,
        )
        verif_retry = verify_citations(answer=retry_res.content, sources=sources, db=db)

        tool_trace.append({"retry": True})
        tool_trace.extend(retry_res.tool_trace)
        degraded = degraded or retry_res.degraded
        if retry_res.artifact:
            artifact_data = retry_res.artifact

        if verif_retry.needs_retry or (not verif_retry.is_refusal and len(verif_retry.citations) == 0):
            # Second attempt still has zero citations on non-refusal — force exact refusal
            logger.warning("Second attempt also failed citation verification — forcing refusal")
            final_content = EXACT_REFUSAL_MESSAGE
            final_citations: List[CitationItem] = []
        else:
            final_content = verif_retry.cleaned_text
            final_citations = verif_retry.citations
    else:
        final_content = verif.cleaned_text
        final_citations = verif.citations

    # 10b. ESSAY deterministic fallback — if intent is ESSAY and no artifact yet, run skill directly
    essay_artifact_data: Optional[dict] = None
    if intent == Intent.ESSAY and not artifact_data:
        logger.info("ESSAY intent: agent did not return artifact — running ship30 skill fallback")
        try:
            from app.skills.ship30 import generate_essay
            topic = body.content.strip()
            essay_result = await generate_essay(topic=topic, sources=sources, provider=provider)
            essay_artifact_data = {
                "type": "markdown",
                "title": f"Ship 30 Essay: {topic[:60]}",
                "content": essay_result.content,
                "word_count": essay_result.word_count,
                "validation_report": {
                    "passed": essay_result.report.passed,
                    "failed_rules": essay_result.report.failed_rules,
                },
                "repaired": essay_result.repaired,
            }
            tool_trace.append({"action": "ship30_fallback", "word_count": essay_result.word_count})
            # Replace final_content with a summary pointing to the artifact
            wc = essay_result.word_count
            rule_summary = (
                "All Ship 30 rules passed."
                if essay_result.report.passed
                else f"Validation: {', '.join(essay_result.report.failed_rules)} flagged."
            )
            final_content = (
                f"Here's your Ship 30 essay on **{topic[:80]}** "
                f"({wc} words). {rule_summary}"
            )
            final_citations = []
        except Exception as exc:
            logger.warning("Ship 30 fallback failed: %s", exc)

    # 11. Artifact persistence
    artifact_record = None
    if essay_artifact_data:
        artifact_record = Artifact(
            session_id=session_id,
            type="markdown",
            title=essay_artifact_data["title"],
            content=essay_artifact_data["content"],
        )
        db.add(artifact_record)
        await db.flush()
    elif artifact_data and isinstance(artifact_data, dict):
        artifact_record = Artifact(
            session_id=session_id,
            type="html",
            title=artifact_data.get("title", "Generated Artifact"),
            content=artifact_data.get("html", ""),
        )
        db.add(artifact_record)
        await db.flush()

    # 12. Persist assistant message
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    assistant_msg = Message(
        id=uuid.uuid4(),
        session_id=session_id,
        role="assistant",
        content=final_content,
        intent=intent.value,
        citations=[c.model_dump(mode="json") for c in final_citations],
        created_at=utc_now(),
        tool_trace=tool_trace,
        degraded=degraded,
        latency_ms=elapsed_ms,
    )
    if artifact_record:
        assistant_msg.artifacts.append(artifact_record)

    db.add(assistant_msg)
    await db.commit()
    await db.refresh(assistant_msg)

    # Build artifact response: prefer essay artifact, then agent artifact
    artifact_response = None
    if artifact_record:
        artifact_response = {
            "id": str(artifact_record.id),
            "title": artifact_record.title,
            "type": artifact_record.type,
        }
    elif artifact_data and isinstance(artifact_data, dict):
        artifact_response = artifact_data

    return ChatResponse(
        message=MessageResponse.model_validate(assistant_msg),
        citations=final_citations,
        intent=intent.value,
        degraded=degraded,
        latency_ms=elapsed_ms,
        artifact=artifact_response,
    )

