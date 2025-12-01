import json
import logging
import sys
from typing import Any, Dict


class JsonFormatter(logging.Formatter):
    """Formatter that emits structured JSON logs."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        payload: Dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "time": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S%z"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if isinstance(record.args, dict):
            payload.update(record.args)
        if hasattr(record, "extra_data"):
            extra_data = getattr(record, "extra_data")
            if isinstance(extra_data, dict):
                payload.update(extra_data)
        return json.dumps(payload)


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure root logging with JSON formatting."""

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=level, handlers=[handler], force=True)
    logger = logging.getLogger("heating_machine")
    logger.debug("Structured logging configured", extra={"extra_data": {"level": level}})
    return logger
