"""Structured JSON logging configuration."""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include custom structured attributes if present
        for key in (
            "request_id",
            "session_id",
            "intent",
            "provider",
            "model",
            "retrieval_ms",
            "llm_ms",
            "total_ms",
            "n_chunks",
            "top_score",
            "degraded",
            "error_code",
            "input_tokens",
        ):
            if hasattr(record, key):
                log_obj[key] = getattr(record, key)

        if record.exc_info and record.levelno >= logging.ERROR:
            # Format exception only for error level
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj)


def setup_logging(log_level: str = "INFO") -> None:
    """Configures the root logger with the JSON formatter."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    # Replace existing handlers
    root_logger.handlers = [handler]
