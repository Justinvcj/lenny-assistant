"""Standardized application error models and exception handlers."""

import logging

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ErrorDetail(BaseModel):
    code: str
    message: str
    status_code: int | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


class AppException(Exception):
    def __init__(self, code: str, message: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "status_code": exc.status_code,
            }
        },
    )


async def db_connection_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Database connection failure: %s: %s", type(exc).__name__, exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "error": {
                "code": "db_unavailable",
                "message": "Database service is temporarily unavailable",
                "status_code": 503,
            }
        },
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Summarize validation errors without leaking internal stack traces
    errors = exc.errors()
    msg = "; ".join([f"{'.'.join(str(loc) for loc in err.get('loc', []))}: {err.get('msg')}" for err in errors])
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "validation_error",
                "message": msg or "Invalid request parameters",
                "status_code": 422,
            }
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception: %s: %s", type(exc).__name__, exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "internal_server_error",
                "message": "An unexpected internal server error occurred",
                "status_code": 500,
            }
        },
    )
