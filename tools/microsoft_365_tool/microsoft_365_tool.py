"""
title: Microsoft 365
id: microsoft_365
author: Justin Kropp
author_url: https://github.com/jrkropp
git_url: https://github.com/jrkropp/open-webui-developer-toolkit/tree/development/tools/microsoft_365_tool
description: Access your Microsoft 365 files, emails, calendar, and Teams directly from Open WebUI.
version: 0.1.0
license: MIT
"""

import os
import json
import base64
import hashlib
from typing import Annotated, Any, Dict, Optional, Literal
from urllib.parse import urlparse


import aiohttp
from cryptography.fernet import Fernet
from pydantic import Field


class Tools:
    def __init__(self):
        MicrosoftAuth.install()  # idempotent

    async def get_profile(self, __request__) -> str:
        """
        Return the signed-in Microsoft 365 user's profile.
        """
        try:
            # No response passed; MicrosoftAuth handles rotation internally.
            data = await MicrosoftAuth.graph_get(__request__, "/me")
            result = {
                "id": data.get("id"),
                "displayName": data.get("displayName"),
                "mail": data.get("mail"),
                "userPrincipalName": data.get("userPrincipalName"),
                "jobTitle": data.get("jobTitle"),
            }
            return json.dumps({"ok": True, "result": result}, indent=2)
        except MicrosoftAuth.Error as e:
            return json.dumps({"ok": False, "error": str(e)}, indent=2)

    async def search_documents(
        self,
        query: str,
        size: int = Field(20, ge=1, le=50, description="Number of results to return (1–50)."),
        offset: int = Field(0, ge=0, description="Paging offset; corresponds to Microsoft Graph 'from'."),
        entity: Literal["files", "items", "sites", "all"] = "files",
        __request__=None,
    ) -> str:
        """
        Search SharePoint/OneDrive documents by keyword.
        :param query: Search text
        :param limit: Number of results to return (1-50)
        :param cursor: Paging token from a previous call
        :return: JSON string with results
        """
        try:
            # ---- sanitize inputs ----
            page_size = max(1, min(int(size), 50))
            start = max(0, int(offset))
            ent = (entity or "files").lower()
            if ent not in ("files", "items", "sites", "all"):
                ent = "files"
            q_string = (query or "*").strip()

            # ---- map tool 'entity' -> Graph Search 'entityTypes' ----
            entity_types_map = {
                "files": ["driveItem"],
                "items": ["listItem"],
                "sites": ["site"],
                "all": ["driveItem", "listItem", "list", "site"],
            }
            entity_types = entity_types_map[ent]

            # ---- call Microsoft Graph Search ----
            body = {
                "requests": [
                    {
                        "entityTypes": entity_types,
                        "query": {"queryString": q_string},
                        "from": start,
                        "size": page_size,
                    }
                ]
            }
            data = await MicrosoftAuth.graph_post(__request__, "/search/query", json=body)

            # ---- flatten hits ----
            hits = []
            for v in data.get("value") or []:
                for c in v.get("hitsContainers") or []:
                    hits.extend(c.get("hits") or [])

            # ---- build friendly markdown block inline ----
            lines = []
            label = {"files": "documents", "items": "items", "sites": "sites", "all": "results"}[ent]
            lines.append(f"**{min(len(hits), page_size)} {label}** for **{q_string}** (from {start})\n")
            lines.append("The following sites were found:" if ent == "sites" else "The following documents were found:")

            if not hits:
                lines.append("* _No results found._")
            else:
                for h in hits[:page_size]:
                    res = h.get("resource") or {}
                    otype = (res.get("@odata.type") or "").lower()

                    # fields
                    name = res.get("name") or res.get("displayName") or (res.get("fields") or {}).get("title") or "Untitled"
                    web = res.get("webUrl") or ""
                    title = f"[{name}]({web})" if web else name

                    fs = res.get("fileSystemInfo") or {}
                    modified = res.get("lastModifiedDateTime") or fs.get("lastModifiedDateTime") or ""
                    date_str = modified[:10] if isinstance(modified, str) and len(modified) >= 10 else "unknown date"

                    size_bytes = res.get("size")
                    if isinstance(size_bytes, int):
                        if size_bytes < 1024:
                            size_str = f"{size_bytes} B"
                        elif size_bytes < 1048576:
                            size_str = f"{size_bytes/1024:.0f} KB"
                        else:
                            size_str = f"{size_bytes/1048576:.1f} MB"
                    else:
                        size_str = "-"

                    is_file = bool(res.get("file"))
                    is_folder = bool(res.get("folder"))
                    kind = (
                        "document" if is_file
                        else "folder" if is_folder
                        else "list item" if otype.endswith("listitem")
                        else "list" if otype.endswith("list")
                        else "site" if otype.endswith("site")
                        else "item"
                    )

                    ext = name.rsplit(".", 1)[-1].lower() if is_file and "." in name else ""
                    meta_parts = [kind]
                    if ext:
                        meta_parts.append(f".{ext}")
                    if date_str:
                        meta_parts.append(f"modified {date_str}")
                    if size_str != "-":
                        meta_parts.append(size_str)
                    meta = " · ".join(meta_parts)

                    snippet = h.get("summary") or ""
                    if snippet:
                        snippet = snippet.replace("<ddd/>", " … ").replace("<c0>", "").replace("</c0>", "")
                        snippet = " ".join(snippet.split())
                        if len(snippet) > 200:
                            snippet = snippet[:197] + "…"

                    lines.append(f"* {title} — {meta}")
                    if snippet:
                        lines.append(f"  - snippet: {snippet}")

            # ---- footer: guidance + paging hint ----
            lines.append("")
            lines.append("_Tips:_ Use the links above when citing.")
            if hits:
                lines.append(f"_Paging:_ Re-run with `offset={start + min(len(hits), page_size)}` and `size={page_size}` to see more.")

            return "\n".join(lines)

        except MicrosoftAuth.Error as e:
            return f"Search failed: {e}"


# ----------------------------------------------------------------
# Minimal Microsoft Graph client with OAuth patch for Open WebUI


class MicrosoftAuth:
    """
    Minimal, self-contained Graph client for Open WebUI + Azure SSO.
    - Captures refresh_token during OAuth callback, stores encrypted in __Host- cookie.
    - Redeems refresh_token for access_token on demand.
    """

    __version__ = "2025.08.25"

    # --- Required config from environment ---
    TENANT = os.getenv("MICROSOFT_CLIENT_TENANT_ID", "").strip()
    CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID", "").strip()
    CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET", "").strip()
    SCOPES = os.getenv("MICROSOFT_OAUTH_SCOPE", "").strip()
    WEBUI_SECRET = os.getenv("WEBUI_SECRET_KEY", "").strip()

    # --- Constants ---
    PROVIDER = "microsoft"
    COOKIE_NAME = "__Host-ms_graph"
    MAX_AGE = 90 * 24 * 3600
    GRAPH_BASE = "https://graph.microsoft.com/v1.0"
    TOKEN_URL = f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token"
    TIMEOUT = aiohttp.ClientTimeout(total=20)
    USER_AGENT = f"OpenWebUI-MicrosoftAuth/{__version__}"

    # --- Crypto ---
    if not WEBUI_SECRET:
        _FERNET = None
    else:
        _FERNET = Fernet(
            base64.urlsafe_b64encode(
                hashlib.sha256(WEBUI_SECRET.encode("utf-8")).digest()
            )
        )

    _PATCHED = False

    class Error(Exception):
        pass

    # --- Install a tiny, safe monkey patch ---
    @classmethod
    def install(cls) -> None:
        if cls._PATCHED:
            return
        try:
            from open_webui.utils.oauth import OAuthManager  # type: ignore
        except Exception:
            # If OAuthManager is unavailable, we can't capture the token during login.
            # Existing cookie (if present) will still work.
            return

        orig_get_client = OAuthManager.get_client
        orig_handle_cb = OAuthManager.handle_callback

        def patched_get_client(self_, provider):
            client = orig_get_client(self_, provider)
            if provider == MicrosoftAuth.PROVIDER and hasattr(
                client, "authorize_access_token"
            ):
                orig = client.authorize_access_token

                async def wrapped_authorize_access_token(request, *args, **kwargs):
                    tok = await orig(request, *args, **kwargs)
                    try:
                        request.state._ms_provider_token = (
                            tok  # stash full token result
                        )
                    except Exception:
                        pass
                    return tok

                # Avoid double-wrapping
                if (
                    getattr(client.authorize_access_token, "__name__", "")
                    != "wrapped_authorize_access_token"
                ):
                    client.authorize_access_token = wrapped_authorize_access_token
            return client

        async def patched_handle_callback(self_, request, provider, response):
            resp = await orig_handle_cb(self_, request, provider, response)
            if provider == MicrosoftAuth.PROVIDER and MicrosoftAuth._FERNET:
                try:
                    tok = getattr(
                        getattr(request, "state", object()), "_ms_provider_token", None
                    )
                    rt = isinstance(tok, dict) and tok.get("refresh_token")
                    if rt:
                        payload = json.dumps({"rt": rt}, separators=(",", ":")).encode(
                            "utf-8"
                        )
                        enc = MicrosoftAuth._FERNET.encrypt(payload).decode("utf-8")
                        resp.set_cookie(
                            key=MicrosoftAuth.COOKIE_NAME,
                            value=enc,
                            httponly=True,
                            secure=True,
                            samesite="Strict",
                            max_age=MicrosoftAuth.MAX_AGE,
                            path="/",
                        )
                except Exception:
                    # Never break login due to cookie issues
                    pass
            return resp

        OAuthManager.get_client = patched_get_client
        OAuthManager.handle_callback = patched_handle_callback
        cls._PATCHED = True

    # --- Best-effort response discovery (so callers don't need to pass one) ---
    @staticmethod
    def _infer_response(request: Any, provided: Any = None) -> Any | None:
        if provided is not None:
            return provided
        # Common places frameworks stash a response object
        candidates = []
        for obj in (request, getattr(request, "state", None)):
            if not obj:
                continue
            for name in (
                "response",
                "_response",
                "fastapi_response",
                "starlette_response",
                "res",
            ):
                try:
                    cand = getattr(obj, name, None)
                    if cand is not None:
                        candidates.append(cand)
                except Exception:
                    pass
        return candidates[0] if candidates else None

    # --- Access token from refresh cookie (auto-rotates cookie if possible) ---
    @classmethod
    async def _access_token(cls, request: Any, response: Any = None) -> str:
        if not cls._FERNET:
            raise cls.Error("WEBUI_SECRET_KEY missing (encryption unavailable).")
        if not (cls.TENANT and cls.CLIENT_ID and cls.CLIENT_SECRET):
            raise cls.Error(
                "Set MICROSOFT_CLIENT_TENANT_ID, MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET."
            )

        enc = getattr(request, "cookies", {}).get(cls.COOKIE_NAME)
        if not enc:
            raise cls.Error(
                f"Missing {cls.COOKIE_NAME} cookie. Sign in with Microsoft."
            )

        try:
            payload = cls._FERNET.decrypt(enc.encode("utf-8")).decode("utf-8")
            rt = json.loads(payload)["rt"]
        except Exception:
            raise cls.Error("Invalid or undecryptable token cookie.")

        form = {
            "client_id": cls.CLIENT_ID,
            "client_secret": cls.CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": rt,
            "scope": cls.SCOPES,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(cls.TOKEN_URL, data=form, timeout=cls.TIMEOUT) as r:
                if r.status != 200:
                    raise cls.Error(await cls._err_text(r))
                data = await r.json()

        at = data.get("access_token")
        if not at:
            raise cls.Error("Token refresh returned no access_token.")

        # Try to rotate the cookie when Microsoft returns a new refresh token
        new_rt = data.get("refresh_token")
        resp_obj = cls._infer_response(request, provided=response)
        if resp_obj is not None and new_rt and new_rt != rt and cls._FERNET:
            try:
                enc2 = cls._FERNET.encrypt(
                    json.dumps({"rt": new_rt}, separators=(",", ":")).encode("utf-8")
                ).decode("utf-8")
                resp_obj.set_cookie(
                    key=cls.COOKIE_NAME,
                    value=enc2,
                    httponly=True,
                    secure=True,
                    samesite="Strict",
                    max_age=cls.MAX_AGE,
                    path="/",
                )
            except Exception:
                # Non-fatal: continue without rotation
                pass

        return at

    # --- Minimal Graph GET (accepts @odata.nextLink absolute URLs) ---
    @classmethod
    async def graph_get(
        cls,
        request: Any,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        # Build URL, allowing only Graph absolute URLs (e.g., @odata.nextLink)
        use_params = params
        if "://" in (path or ""):
            u = urlparse(path)
            base_host = urlparse(cls.GRAPH_BASE).netloc
            if u.scheme != "https" or u.netloc != base_host:
                raise cls.Error(
                    "Only Microsoft Graph URLs are allowed for absolute paths."
                )
            url = path
            # nextLink already contains its own query; don't double-append params
            use_params = None
        else:
            if not path.startswith("/"):
                path = "/" + path
            url = cls.GRAPH_BASE + path

        token = await cls._access_token(request)
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": cls.USER_AGENT,
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, params=use_params, headers=headers, timeout=cls.TIMEOUT
            ) as resp:
                if 200 <= resp.status < 300:
                    try:
                        return await resp.json()
                    except Exception:
                        return {}
                raise cls.Error(await cls._err_text(resp))

    # --- Minimal Graph POST (JSON or raw body; allows absolute Graph URLs) ---
    @classmethod
    async def graph_post(
        cls,
        request: Any,
        path: str,
        *,
        json: Any = None,
        data: Any = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        # Build URL, allowing only Microsoft Graph absolute URLs
        use_params = params
        if "://" in (path or ""):
            u = urlparse(path)
            base_host = urlparse(cls.GRAPH_BASE).netloc
            if u.scheme != "https" or u.netloc != base_host:
                raise cls.Error(
                    "Only Microsoft Graph URLs are allowed for absolute paths."
                )
            url = path
            # Absolute nextLink/URLs already include their own querystring
            use_params = None
        else:
            if not path.startswith("/"):
                path = "/" + path
            url = cls.GRAPH_BASE + path

        token = await cls._access_token(request)
        h = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": cls.USER_AGENT,
        }
        # Set Content-Type automatically when sending JSON unless caller overrides
        if json is not None and not (headers and "Content-Type" in headers):
            h["Content-Type"] = "application/json"
        if headers:
            h.update(headers)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                params=use_params,
                json=json,
                data=data,
                headers=h,
                timeout=cls.TIMEOUT,
            ) as resp:
                if 200 <= resp.status < 300:
                    # Prefer JSON; fall back to text for non-JSON responses
                    ct = resp.headers.get("Content-Type", "")
                    if "application/json" in ct:
                        try:
                            return await resp.json()
                        except Exception:
                            return {}
                    return {
                        "ok": True,
                        "status": resp.status,
                        "text": await resp.text(),
                    }
                raise cls.Error(await cls._err_text(resp))

    # --- Logout helper ---
    @classmethod
    def clear_cookie(cls, response: Any) -> None:
        response.delete_cookie(cls.COOKIE_NAME, path="/")

    # --- Single error extractor for both token + Graph responses ---
    @staticmethod
    async def _err_text(resp: aiohttp.ClientResponse) -> str:
        try:
            j = await resp.json()
            if isinstance(j, dict):
                return (
                    j.get("error_description")
                    or j.get("message")
                    or (isinstance(j.get("error"), dict) and j["error"].get("message"))
                    or f"HTTP {resp.status}"
                )
        except Exception:
            pass
        return f"HTTP {resp.status}"
