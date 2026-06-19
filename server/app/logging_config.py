"""Structured (JSON-line) logging. One log = one JSON object on stdout.

Keeping this dependency-free (no python-json-logger) so the image stays small and
the format is fully under our control.
"""
import json
import logging
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Attach any structured fields passed via logger.info(..., extra={"extra_fields": {...}}).
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    # Uvicorn access logs are noisy and unstructured; we emit our own access log.
    logging.getLogger("uvicorn.access").disabled = True


def log_event(logger: logging.Logger, msg: str, **fields) -> None:
    """Emit a structured log line with arbitrary key/value fields."""
    logger.info(msg, extra={"extra_fields": fields})
