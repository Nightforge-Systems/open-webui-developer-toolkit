"""Model capability registry and alias helpers."""

from __future__ import annotations

import re
from typing import Any, ClassVar


class ModelFamily:
    """Central registry of model capabilities and alias metadata."""

    _DATE_RE = re.compile(r"-\d{4}-\d{2}-\d{2}$")
    _PREFIX = "openai_responses."

    _SPECS: ClassVar[dict[str, dict[str, Any]]] = {
        "gpt-5-auto": {
            "features": {
                "function_calling",
                "reasoning",
                "reasoning_summary",
                "web_search_tool",
                "image_gen_tool",
                "verbosity",
            }
        },
        "gpt-5": {
            "features": {
                "function_calling",
                "reasoning",
                "reasoning_summary",
                "web_search_tool",
                "image_gen_tool",
                "verbosity",
            }
        },
        "gpt-5-mini": {
            "features": {
                "function_calling",
                "reasoning",
                "reasoning_summary",
                "web_search_tool",
                "image_gen_tool",
                "verbosity",
            }
        },
        "gpt-5-nano": {
            "features": {
                "function_calling",
                "reasoning",
                "reasoning_summary",
                "web_search_tool",
                "image_gen_tool",
                "verbosity",
            }
        },
        "gpt-4.1": {"features": {"function_calling", "web_search_tool", "image_gen_tool"}},
        "gpt-4.1-mini": {"features": {"function_calling", "web_search_tool", "image_gen_tool"}},
        "gpt-4.1-nano": {"features": {"function_calling", "image_gen_tool"}},
        "gpt-4o": {"features": {"function_calling", "web_search_tool", "image_gen_tool"}},
        "gpt-4o-mini": {"features": {"function_calling", "web_search_tool", "image_gen_tool"}},
        "o3": {"features": {"function_calling", "reasoning", "reasoning_summary"}},
        "o3-mini": {"features": {"function_calling", "reasoning", "reasoning_summary"}},
        "o3-pro": {"features": {"function_calling", "reasoning"}},
        "o4-mini": {
            "features": {"function_calling", "reasoning", "reasoning_summary", "web_search_tool"}
        },
        "o3-deep-research": {
            "features": {"function_calling", "reasoning", "reasoning_summary", "deep_research"}
        },
        "o4-mini-deep-research": {
            "features": {"function_calling", "reasoning", "reasoning_summary", "deep_research"}
        },
        "gpt-5-chat-latest": {"features": {"function_calling", "web_search_tool"}},
        "chatgpt-4o-latest": {"features": set()},
    }

    _ALIASES: ClassVar[dict[str, dict[str, Any]]] = {
        "gpt-5-thinking": {"base_model": "gpt-5"},
        "gpt-5-thinking-minimal": {
            "base_model": "gpt-5",
            "params": {"reasoning": {"effort": "minimal"}},
        },
        "gpt-5-thinking-high": {"base_model": "gpt-5", "params": {"reasoning": {"effort": "high"}}},
        "gpt-5-thinking-mini": {"base_model": "gpt-5-mini"},
        "gpt-5-thinking-mini-minimal": {
            "base_model": "gpt-5-mini",
            "params": {"reasoning": {"effort": "minimal"}},
        },
        "gpt-5-thinking-mini-high": {
            "base_model": "gpt-5-mini",
            "params": {"reasoning": {"effort": "high"}},
        },
        "gpt-5-thinking-nano": {"base_model": "gpt-5-nano"},
        "gpt-5-thinking-nano-minimal": {
            "base_model": "gpt-5-nano",
            "params": {"reasoning": {"effort": "minimal"}},
        },
        "gpt-5-thinking-nano-high": {
            "base_model": "gpt-5-nano",
            "params": {"reasoning": {"effort": "high"}},
        },
        "o3-mini-high": {"base_model": "o3-mini", "params": {"reasoning": {"effort": "high"}}},
        "o4-mini-high": {"base_model": "o4-mini", "params": {"reasoning": {"effort": "high"}}},
    }

    @classmethod
    def _norm(cls, model_id: str) -> str:
        value = (model_id or "").strip()
        if value.startswith(cls._PREFIX):
            value = value[len(cls._PREFIX) :]
        return cls._DATE_RE.sub("", value.lower())

    @classmethod
    def base_model(cls, model_id: str) -> str:
        """Return the canonical base model for the given id or alias."""
        key = cls._norm(model_id)
        base = cls._ALIASES.get(key, {}).get("base_model")
        return cls._norm(base or key)

    @classmethod
    def params(cls, model_id: str) -> dict[str, Any]:
        """Return defaults implied by aliases (e.g., reasoning effort)."""
        key = cls._norm(model_id)
        return dict(cls._ALIASES.get(key, {}).get("params", {}))

    @classmethod
    def features(cls, model_id: str) -> frozenset[str]:
        """Capabilities for the base model behind this id or alias."""
        return frozenset(cls._SPECS.get(cls.base_model(model_id), {}).get("features", set()))

    @classmethod
    def supports(cls, feature: str, model_id: str) -> bool:
        """Check if a model (alias or base) supports a given feature."""
        return feature in cls.features(model_id)
