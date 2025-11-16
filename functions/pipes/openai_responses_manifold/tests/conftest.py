"""Ensure tests import the current single-file manifold implementation."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any


def _install_open_webui_stubs() -> None:
    """Create lightweight stand-ins for the open_webui modules used during import."""

    def _ensure_module(name: str) -> ModuleType:
        if name in sys.modules:
            return sys.modules[name]  # type: ignore[return-value]
        module = ModuleType(name)
        sys.modules[name] = module
        return module

    open_webui_pkg = _ensure_module("open_webui")
    models_pkg = _ensure_module("open_webui.models")
    chats_mod = _ensure_module("open_webui.models.chats")
    models_mod = _ensure_module("open_webui.models.models")
    utils_pkg = _ensure_module("open_webui.utils")
    misc_mod = _ensure_module("open_webui.utils.misc")

    class _Chats:
        @staticmethod
        def get_chat_by_id(chat_id: str) -> SimpleNamespace | None:  # pragma: no cover - stub
            return None

        @staticmethod
        def update_chat_by_id(
            chat_id: str, payload: dict[str, Any]
        ) -> None:  # pragma: no cover - stub
            return None

        @staticmethod
        def upsert_message_to_chat_by_id_and_message_id(
            chat_id: str, message_id: str, payload: dict[str, Any]
        ) -> None:  # pragma: no cover - stub
            return None

    class _Models:
        @staticmethod
        def get_model_by_id(model_id: str) -> None:  # pragma: no cover - stub
            return None

        @staticmethod
        def update_model_by_id(model_id: str, form: Any) -> None:  # pragma: no cover - stub
            return None

    class _ModelForm:
        def __init__(self, **kwargs: Any) -> None:
            self._kwargs = kwargs

        def model_dump(self) -> dict[str, Any]:  # pragma: no cover - stub
            return dict(self._kwargs)

    def _get_last_user_message(
        messages: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:  # pragma: no cover - stub
        return (messages or [{}])[-1]

    chats_mod.Chats = _Chats
    models_mod.Models = _Models
    models_mod.ModelForm = _ModelForm
    misc_mod.get_last_user_message = _get_last_user_message

    open_webui_pkg.models = models_pkg
    models_pkg.chats = chats_mod
    models_pkg.models = models_mod
    open_webui_pkg.utils = utils_pkg
    utils_pkg.misc = misc_mod

    aiohttp_mod = _ensure_module("aiohttp")

    class _DummyContent:
        async def iter_chunked(self, _: int) -> Any:
            if False:  # pragma: no cover - placeholder generator
                yield b""

    class _DummyResponse:
        def __init__(self) -> None:
            self.content = _DummyContent()

        async def __aenter__(self) -> _DummyResponse:  # pragma: no cover - stub
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - stub
            return None

        def raise_for_status(self) -> None:  # pragma: no cover - stub
            return None

        async def json(self) -> dict[str, Any]:
            return {}

    class _ClientSession:
        def __init__(self, *_, **__) -> None:
            self.closed = False

        async def close(self) -> None:
            self.closed = True

        def post(self, *_, **__) -> _DummyResponse:
            return _DummyResponse()

    class _TCPConnector:
        def __init__(self, *_, **__) -> None:  # pragma: no cover - stub
            return None

    class _ClientTimeout:
        def __init__(self, *_, **__) -> None:  # pragma: no cover - stub
            return None

    aiohttp_mod.ClientSession = _ClientSession
    aiohttp_mod.TCPConnector = _TCPConnector
    aiohttp_mod.ClientTimeout = _ClientTimeout


def _load_monolith_module() -> None:
    module_path = Path(__file__).resolve().parents[1] / "openai_responses_manifold.py"
    spec = importlib.util.spec_from_file_location("openai_responses_manifold", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules["openai_responses_manifold"] = module


_install_open_webui_stubs()
_load_monolith_module()
