"""Health check and public config endpoints."""

import logging
from typing import Any, Dict
import httpx
from fastapi import APIRouter, Response, status
from sqlalchemy import text
from app.config import get_settings

router = APIRouter(tags=["system"])
logger = logging.getLogger(__name__)


@router.get("/health")
async def health_check(response: Response) -> Dict[str, Any]:
    settings = get_settings()
    db_ok = False
    vector_count = 0
    ollama_ok = False
    llm_model_present = False
    embedding_model_present = False

    # 1. Database check
    try:
        from app.db import async_session_factory
        if async_session_factory:
            async with async_session_factory() as session:
                await session.execute(text("SELECT 1"))
                db_ok = True
                # Check vector count if chunks table exists
                try:
                    res = await session.execute(text("SELECT count(*) FROM chunks"))
                    vector_count = res.scalar() or 0
                except Exception:
                    vector_count = 0
    except Exception as exc:
        logger.warning(f"Database health check failed: {exc}")
        db_ok = False

    provider_reason = None

    # 2. Provider check
    if settings.llm_provider == "ollama":
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{settings.ollama_base_url}/api/tags")
                if res.status_code == 200:
                    ollama_ok = True
                    models = [m.get("name") for m in res.json().get("models", [])]
                    # Check without tag suffix or with exact match
                    llm_model_present = any(settings.llm_model in m for m in models)
                    embedding_model_present = any(settings.embedding_model in m for m in models)
                else:
                    ollama_ok = False
                    provider_reason = "ollama_unreachable"
        except Exception as exc:
            logger.warning(f"Ollama health check failed: {exc}")
            ollama_ok = False
            provider_reason = "ollama_unreachable"
    elif settings.llm_provider == "anthropic":
        embedding_model_present = True
        try:
            from app.llm.factory import get_provider

            provider = get_provider("anthropic")
            p_health = await provider.health()
            if p_health.ok:
                ollama_ok = True
                llm_model_present = True
            else:
                ollama_ok = False
                llm_model_present = False
                provider_reason = p_health.error or "anthropic_degraded"
        except Exception as exc:
            logger.warning(f"Anthropic health check failed: {exc}")
            ollama_ok = False
            llm_model_present = False
            provider_reason = str(exc)
    else:
        ollama_ok = False
        llm_model_present = False
        embedding_model_present = False
        provider_reason = f"unknown_provider_{settings.llm_provider}"

    # Status determination:
    # HTTP 503 ONLY if the database is down per SPEC / P1
    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        overall_status = "degraded"
        reason_val = "database_down"
    elif not ollama_ok or not llm_model_present or not embedding_model_present:
        overall_status = "degraded"
        reason_val = provider_reason or "model_unavailable"
    else:
        overall_status = "ok"
        reason_val = None

    is_ingested = bool(vector_count > 0)

    payload: Dict[str, Any] = {
        "status": overall_status,
        "ingested": is_ingested,
        "database": {
            "connected": db_ok,
            "vector_count": vector_count,
            "ingested": is_ingested,
        },
        "provider": {
            "name": settings.llm_provider,
            "model": settings.llm_model,
            "ok": (overall_status == "ok"),
            "status": overall_status,
            "reason": reason_val,
        },
        "ollama": {
            "reachable": ollama_ok,
            "llm_model_present": llm_model_present,
            "embedding_model_present": embedding_model_present,
            "llm_model": settings.llm_model,
            "embedding_model": settings.embedding_model,
            "reason": reason_val,
        },
    }
    if reason_val:
        payload["reason"] = reason_val

    return payload


@router.get("/config")
async def get_public_config() -> Dict[str, Any]:
    settings = get_settings()
    return {
        "provider": settings.llm_provider,
        "model": settings.llm_model,
        "embedding_model": settings.embedding_model,
        "embedding_dim": settings.embedding_dim,
    }
