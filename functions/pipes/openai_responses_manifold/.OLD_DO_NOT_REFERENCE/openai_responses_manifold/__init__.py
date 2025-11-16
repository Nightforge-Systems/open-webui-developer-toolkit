"""Lazy imports for the real manifold package."""

from __future__ import annotations

from importlib import import_module


def __getattr__(name: str) -> object:
    if name == "Pipe":
        module = import_module(".pipe", __name__)
        return module.Pipe
    message = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(message)


__all__ = ["Pipe"]
