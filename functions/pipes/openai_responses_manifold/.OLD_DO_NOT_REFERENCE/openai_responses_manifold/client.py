"""HTTP client wrapper for the OpenAI Responses API."""

from __future__ import annotations

import json
import logging
from time import perf_counter
from typing import TYPE_CHECKING, Any

import aiohttp

from .logging_utils import compact_json, summarize_request

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from .models import ResponsesRequest


class ResponsesClient:
    """Tiny wrapper around aiohttp for the Responses API."""

    def __init__(self, api_key: str, base_url: str) -> None:
        """Store credentials and lazily-created session state."""
        self.api_key = api_key
        self.base_url = base_url.rstrip("/") or "https://api.openai.com/v1"
        self._session: aiohttp.ClientSession | None = None
        self.logger = logging.getLogger(__name__)

    async def close(self) -> None:
        """Close the cached aiohttp session if it is still open."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _session_or_create(self) -> aiohttp.ClientSession:
        """Return the cached session or create a new one with sane defaults."""
        if self._session and not self._session.closed:
            return self._session
        connector = aiohttp.TCPConnector(
            limit=50,
            limit_per_host=10,
            keepalive_timeout=75,
            ttl_dns_cache=300,
        )
        timeout = aiohttp.ClientTimeout(connect=30, sock_connect=30, sock_read=3600)
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            json_serialize=json.dumps,
        )
        return self._session

    async def stream(self, request: ResponsesRequest) -> AsyncIterator[dict[str, Any]]:
        """Stream SSE frames from the Responses API."""
        session = await self._session_or_create()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        url = f"{self.base_url}/responses"
        payload = request.model_dump(exclude_none=True)
        summary = summarize_request(payload)
        self.logger.info("Opening streaming request: %s", summary)
        timer = perf_counter()
        try:
            async with session.post(url, json=payload, headers=headers) as resp:
                request_id = self._request_id(resp.headers)
                if resp.status >= 400:
                    await self._log_http_error(resp, mode="stream")
                resp.raise_for_status()
                elapsed = perf_counter() - timer
                self.logger.info(
                    "Streaming connection established (status=%s request_id=%s elapsed=%.2fs)",
                    resp.status,
                    request_id,
                    elapsed,
                )
                buffer = bytearray()
                async for chunk in resp.content.iter_chunked(4096):
                    buffer.extend(chunk)
                    start = 0
                    while True:
                        end = buffer.find(b"\n", start)
                        if end == -1:
                            break
                        line = buffer[start:end].strip()
                        start = end + 1
                        if not line or line.startswith(b":"):
                            continue
                        if not line.startswith(b"data:"):
                            continue
                        data = line[5:].strip()
                        if data == b"[DONE]":
                            self.logger.info(
                                "Streaming request complete (request_id=%s)", request_id
                            )
                            return
                        yield json.loads(data.decode("utf-8"))
                    if start:
                        del buffer[:start]
        except aiohttp.ClientError:
            self.logger.exception("Streaming request failed")
            raise

    async def invoke(self, request: ResponsesRequest) -> dict[str, Any]:
        """Execute a plain JSON request and return the parsed payload."""
        session = await self._session_or_create()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/responses"
        payload = request.model_dump(exclude_none=True)
        summary = summarize_request(payload)
        self.logger.info("Invoking Responses API: %s", summary)
        timer = perf_counter()
        try:
            async with session.post(url, json=payload, headers=headers) as resp:
                request_id = self._request_id(resp.headers)
                if resp.status >= 400:
                    await self._log_http_error(resp, mode="invoke")
                resp.raise_for_status()
                data = await resp.json()
                elapsed = perf_counter() - timer
                self.logger.info(
                    "Responses request succeeded (status=%s request_id=%s elapsed=%.2fs)",
                    resp.status,
                    request_id,
                    elapsed,
                )
                return data
        except aiohttp.ClientError:
            self.logger.exception("Responses request failed")
            raise

    @staticmethod
    def _request_id(headers: Any) -> str | None:
        """Return the request identifier header if present."""

        for key in ("x-request-id", "openai-request-id", "request-id"):
            if not isinstance(headers, dict) and hasattr(headers, "get"):
                value = headers.get(key)
            else:
                value = headers.get(key) if isinstance(headers, dict) else None
            if value:
                return str(value)
        return None

    async def _log_http_error(self, resp: aiohttp.ClientResponse, *, mode: str) -> None:
        """Log structured details for non-2xx responses before raising."""

        text = await resp.text()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = text.strip() or "<empty>"
        self.logger.error(
            "%s request failed (status=%s endpoint=%s request_id=%s body=%s)",
            mode,
            resp.status,
            resp.url,
            self._request_id(resp.headers),
            compact_json(payload),
        )


__all__ = ["ResponsesClient"]
