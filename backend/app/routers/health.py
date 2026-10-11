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

    # 2. Ollama check (if provider is ollama)
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
        except Exception as exc:
            logger.warning(f"Ollama health check failed: {exc}")
            ollama_ok = False
    else:
        # Non-ollama provider (e.g. anthropic)
        ollama_ok = True
        llm_model_present = bool(settings.anthropic_api_key)
        embedding_model_present = True

    # Status determination:
    # HTTP 503 ONLY if the database is down per SPEC / P1
    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        overall_status = "degraded"
    elif not ollama_ok or not llm_model_present or not embedding_model_present:
        overall_status = "degraded"
    else:
        overall_status = "ok"

    is_ingested = bool(vector_count > 0)

    return {
        "status": overall_status,
        "ingested": is_ingested,
        "database": {
            "connected": db_ok,
            "vector_count": vector_count,
            "ingested": is_ingested,
        },
        "ollama": {
            "reachable": ollama_ok,
            "llm_model_present": llm_model_present,
            "embedding_model_present": embedding_model_present,
            "llm_model": settings.llm_model,
            "embedding_model": settings.embedding_model,
        },
    }


@router.get("/config")
async def get_public_config() -> Dict[str, Any]:
    settings = get_settings()
    return {
        "provider": settings.llm_provider,
        "model": settings.llm_model,
        "embedding_model": settings.embedding_model,
        "embedding_dim": settings.embedding_dim,
    }
