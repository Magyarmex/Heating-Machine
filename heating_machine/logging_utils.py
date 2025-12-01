import json
import logging
import sys
from collections import deque
from typing import Any, Deque, Dict, List


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


class InMemoryLogHandler(logging.Handler):
    """Simple handler that keeps a bounded buffer of recent JSON log payloads."""

    def __init__(self, capacity: int = 50) -> None:
        super().__init__()
        self.capacity = capacity
        self._buffer: Deque[Dict[str, Any]] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        try:
            payload = self.format(record)
            parsed = json.loads(payload)
            self._buffer.append(parsed)
        except Exception:
            # The buffer should never break the main logging flow
            return

    def recent(self, limit: int | None = None) -> List[Dict[str, Any]]:
        limit = limit or self.capacity
        return list(self._buffer)[-limit:]


_log_buffer = InMemoryLogHandler()


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure root logging with JSON formatting and memory buffer."""

    formatter = JsonFormatter()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    _log_buffer.setFormatter(formatter)
    logging.basicConfig(level=level, handlers=[handler, _log_buffer], force=True)
    logger = logging.getLogger("heating_machine")
    logger.debug("Structured logging configured", extra={"extra_data": {"level": level}})
    return logger


def recent_logs(limit: int = 30) -> List[Dict[str, Any]]:
    """Expose a copy of the most recent log entries for dashboards or tests."""

    return _log_buffer.recent(limit)
