"""FastAPI application entry point."""

import time
import uuid
import logging
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from sqlalchemy.exc import DBAPIError, OperationalError

try:
    import psycopg
    PSYCOPG_ERRORS = (psycopg.OperationalError, psycopg.Error)
except ImportError:
    PSYCOPG_ERRORS = ()

from app.config import get_settings
from app.logging_setup import setup_logging
from app.errors import (
    AppException,
    app_exception_handler,
    db_connection_exception_handler,
    validation_exception_handler,
    unhandled_exception_handler,
)
from app.routers.health import router as health_router
from app.routers.sessions import router as sessions_router
from app.routers.chat import router as chat_router
from app.routers.artifacts import router as artifacts_router
from app.routers.client_events import router as client_events_router

settings = get_settings()
setup_logging(settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Lenny Growth Assistant API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url=None,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request ID and Structured Logging Middleware
class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        start_time = time.perf_counter()

        response = await call_next(request)

        duration_ms = int((time.perf_counter() - start_time) * 1000)
        response.headers["X-Request-ID"] = request_id

        # Log request summary with structured fields
        logger.info(
            f"{request.method} {request.url.path} - {response.status_code} ({duration_ms}ms)",
            extra={
                "request_id": request_id,
                "total_ms": duration_ms,
            },
        )
        return response


app.add_middleware(RequestContextMiddleware)

# Error handlers
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(OperationalError, db_connection_exception_handler)
app.add_exception_handler(DBAPIError, db_connection_exception_handler)
if PSYCOPG_ERRORS:
    for err_cls in PSYCOPG_ERRORS:
        app.add_exception_handler(err_cls, db_connection_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# Routers
app.include_router(health_router)
app.include_router(sessions_router)
app.include_router(chat_router)
app.include_router(artifacts_router)
app.include_router(client_events_router)
