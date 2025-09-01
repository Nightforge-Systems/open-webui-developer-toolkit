"""
title: Prompt Enrichment
id: prompt_enrichment_filter
description: Append user-specific context to the system prompt.
git_url: https://github.com/jrkropp/open-webui-developer-toolkit.git
required_open_webui_version: 0.6.10
version: 0.1.0
"""
from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, Dict

from pydantic import BaseModel, Field


class Filter:
    class Valves(BaseModel):
        CACHE_TTL_SECONDS: int = Field(
            default=3600, description="Seconds before cached user data expires."
        )
        priority: int = Field(
            default=0, description="Priority level for the filter operations."
        )

    def __init__(self) -> None:
        self.valves = self.Valves()
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._redis = None

    # User context storage/retrieval leveraging Open WebUI Memories and Redis
    # - Per-process in-memory cache with TTL for speed
    # - Optional Redis cache (shared across workers) if REDIS_URL is configured
    def _get_redis(self):
        if self._redis is not None:
            return self._redis
        try:
            from open_webui.env import (
                REDIS_URL,
                REDIS_SENTINEL_HOSTS,
                REDIS_SENTINEL_PORT,
                REDIS_CLUSTER,
                REDIS_KEY_PREFIX,
            )
            from open_webui.utils.redis import get_redis_connection, get_sentinels_from_env

            if not REDIS_URL:
                self._redis = None
                self._redis_key_prefix = "open-webui"
                return None

            sentinels = get_sentinels_from_env(REDIS_SENTINEL_HOSTS, REDIS_SENTINEL_PORT)
            self._redis = get_redis_connection(
                redis_url=REDIS_URL,
                redis_sentinels=sentinels,
                redis_cluster=REDIS_CLUSTER,
                async_mode=False,
                decode_responses=True,
            )
            self._redis_key_prefix = f"{REDIS_KEY_PREFIX}:filters:prompt-enrichment"
        except Exception:
            # If anything goes wrong (e.g., module not available in tests), fall back gracefully
            self._redis = None
            self._redis_key_prefix = "open-webui:filters:prompt-enrichment"
        return self._redis

    def _cache_key(self, user_id: str) -> str:
        return f"{getattr(self, '_redis_key_prefix', 'open-webui:filters:prompt-enrichment')}:user:{user_id}"

    def _get_cached_context_local(self, user_id: str) -> str | None:
        now = int(time.time())
        entry = self._cache.get(user_id)
        if entry and entry.get("exp", 0) > now:
            return entry.get("val")
        return None

    def _set_cached_context_local(self, user_id: str, value: str) -> None:
        self._cache[user_id] = {"val": value, "exp": int(time.time()) + int(self.valves.CACHE_TTL_SECONDS)}

    def _get_cached_context_redis(self, user_id: str) -> str | None:
        r = self._get_redis()
        if not r:
            return None
        try:
            return r.get(self._cache_key(user_id))
        except Exception:
            return None

    def _set_cached_context_redis(self, user_id: str, value: str) -> None:
        r = self._get_redis()
        if not r:
            return
        try:
            ttl = int(self.valves.CACHE_TTL_SECONDS)
            r.set(self._cache_key(user_id), value, ex=ttl)
        except Exception:
            pass

    def _compose_enrichment_prompt(self, user: Dict[str, Any], memories: list[Dict[str, Any]]) -> str:
        name = user.get("name") or user.get("username") or user.get("email") or "user"
        if not memories:
            return f"User context for {name}: No saved memories yet."

        lines = []
        # Keep it concise: include up to the 5 most recent memory contents
        for m in memories[:5]:
            content = (m.get("content") or "").strip()
            if content:
                # Single-line bullet for compactness
                lines.append(f"- {content}")

        if not lines:
            return f"User context for {name}: No saved memories yet."

        return f"User context for {name} (recent memories):\n" + "\n".join(lines)

    def _fetch_user_memories(self, user_id: str) -> list[Dict[str, Any]]:
        try:
            from open_webui.models.memories import Memories

            raw = Memories.get_memories_by_user_id(user_id) or []
            # Convert to dicts and order by updated_at desc, then created_at desc
            items = [
                m.model_dump() if hasattr(m, "model_dump") else dict(m)
                for m in raw
            ]
            items.sort(key=lambda x: (x.get("updated_at") or 0, x.get("created_at") or 0), reverse=True)
            return items
        except Exception:
            return []

    def _get_user_context(self, user: Dict[str, Any]) -> str:
        user_id = str(user.get("id") or user.get("_id") or "")
        if not user_id:
            return ""

        # 1) Fast path: local cache
        val = self._get_cached_context_local(user_id)
        if val is not None:
            return val

        # 2) Shared cache: Redis
        val = self._get_cached_context_redis(user_id)
        if val is not None:
            # Mirror into local cache for faster subsequent hits
            self._set_cached_context_local(user_id, val)
            return val

        # 3) Source of truth: DB memories
        memories = self._fetch_user_memories(user_id)
        val = self._compose_enrichment_prompt(user, memories)

        # 4) Populate caches
        self._set_cached_context_local(user_id, val)
        self._set_cached_context_redis(user_id, val)
        return val

    async def inlet(
        self,
        body: Dict[str, Any],
        __user__: Dict[str, Any],
        __event_emitter__: Callable[[Dict[str, Any]], Awaitable[None]] | None = None,
        __metadata__: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Append cached user information to the system prompt before the manifold."""

        # Build or retrieve the user-specific enrichment prompt
        try:
            enrichment_prompt = self._get_user_context(__user__ or {})
        except Exception:
            enrichment_prompt = ""

        messages = body.setdefault("messages", [])
        for msg in messages:
            if msg.get("role") == "system":
                if enrichment_prompt:
                    msg["content"] = f"{msg.get('content', '')}\n{enrichment_prompt}".strip()
                break
        else:
            if enrichment_prompt:
                messages.insert(0, {"role": "system", "content": enrichment_prompt})

        return body
