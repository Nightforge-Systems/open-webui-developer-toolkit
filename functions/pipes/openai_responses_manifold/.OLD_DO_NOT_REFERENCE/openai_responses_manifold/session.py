"""Request-scoped logging utilities for Open WebUI."""

from __future__ import annotations

import logging
import sys
from collections import defaultdict, deque
from contextvars import ContextVar, Token
from typing import Any, ClassVar

_package_parts = __name__.rsplit(".", 1)


class SessionLogger:
    """Per-request logging that mirrors Open WebUI expectations."""

    BASE_LOGGER = _package_parts[0] if len(_package_parts) > 1 else __name__

    session_id: ContextVar[str | None] = ContextVar("owui_session_id", default=None)
    level: ContextVar[int] = ContextVar("owui_log_level", default=logging.INFO)
    context: ContextVar[dict[str, Any] | None] = ContextVar("owui_log_context", default=None)
    logs: ClassVar[dict[str | None, deque[str]]] = defaultdict(lambda: deque(maxlen=2000))
    _configured: ClassVar[bool] = False

    @classmethod
    def configure_logging(cls) -> None:
        """Configure the package logger exactly once."""
        if cls._configured:
            return
        logger = logging.getLogger(cls.BASE_LOGGER)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        session_filter = _SessionFilter()

        stream = logging.StreamHandler(sys.stdout)
        stream.setFormatter(
            logging.Formatter(
                "[%(levelname)s] [session=%(session_id)s chat=%(chat_id)s model=%(model_id)s req=%(request_model)s msg=%(message_id)s] %(message)s",
            ),
        )
        stream.addFilter(session_filter)
        logger.addHandler(stream)

        buffer = SessionBufferHandler()
        buffer.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] [session=%(session_id)s chat=%(chat_id)s model=%(model_id)s req=%(request_model)s msg=%(message_id)s] %(message)s",
            ),
        )
        buffer.addFilter(session_filter)
        logger.addHandler(buffer)
        cls._configured = True

    @classmethod
    def bind_context(cls, **fields: Any) -> Token[dict[str, Any] | None]:
        """Attach metadata (chat/model/message ids) to subsequent log records."""

        current = dict(cls.context.get() or {})
        for key, value in fields.items():
            if value is None:
                continue
            current[key] = value
        return cls.context.set(current)

    @classmethod
    def reset_context(cls, token: Token[dict[str, Any] | None]) -> None:
        """Restore the previous logging context."""

        cls.context.reset(token)


class _SessionFilter(logging.Filter):
    """Populate log records with the active session id and enforce level."""

    def filter(self, record: logging.LogRecord) -> bool:
        session_id = SessionLogger.session_id.get()
        record._session_key = session_id
        record.session_id = session_id or "-"
        context = SessionLogger.context.get() or {}
        record.chat_id = context.get("chat_id") or "-"
        record.model_id = context.get("model_id") or "-"
        record.message_id = context.get("message_id") or "-"
        record.request_model = context.get("request_model") or "-"
        return record.levelno >= SessionLogger.level.get()


class SessionBufferHandler(logging.Handler):
    """Handler that buffers log output per session."""

    def emit(self, record: logging.LogRecord) -> None:
        session_id = getattr(record, "_session_key", None)
        if not session_id:
            return
        message = self.format(record)
        SessionLogger.logs[session_id].append(message)


SessionLogger.configure_logging()

__all__ = ["SessionLogger"]
