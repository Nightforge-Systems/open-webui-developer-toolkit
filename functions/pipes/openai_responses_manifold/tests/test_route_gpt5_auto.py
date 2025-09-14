import json
import sys
import types
import pytest

# Stub minimal open_webui modules required for import
owui_root = types.ModuleType("open_webui")
models_pkg = types.ModuleType("open_webui.models")
sys.modules.setdefault("open_webui", owui_root)
sys.modules.setdefault("open_webui.models", models_pkg)
sys.modules.setdefault("open_webui.models.chats", types.SimpleNamespace(Chats=object))
sys.modules.setdefault(
    "open_webui.models.models",
    types.SimpleNamespace(ModelForm=object, Models=object),
)

from functions.pipes.openai_responses_manifold.openai_responses_manifold import Pipe, ResponsesBody


@pytest.mark.asyncio
async def test_route_gpt5_auto_updates_body(monkeypatch):
    pipe = Pipe()
    body = ResponsesBody(model="gpt-5-chat-latest", input=[{"role": "user", "content": "hi"}])
    valves = pipe.Valves()

    async def fake_request(params, api_key, base_url):
        assert params["model"] == "gpt-4.1-nano"
        assert params["input"] == "hi"
        assert "instructions" in params
        router_result = {"model": "gpt-5-nano"}
        return {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": json.dumps(router_result)}
                    ],
                }
            ]
        }

    monkeypatch.setattr(
        pipe,
        "send_openai_responses_nonstreaming_request",
        fake_request,
    )

    updated = await pipe._route_gpt5_auto(body, valves)
    assert updated.model == "gpt-5-nano"
