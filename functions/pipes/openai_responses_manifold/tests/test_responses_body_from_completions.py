"""Baseline tests for the CompletionsBody -> ResponsesBody conversion."""

from __future__ import annotations

from openai_responses_manifold import CompletionsBody, ResponsesBody


def test_responses_body_from_completions_maps_reasoning_and_tokens() -> None:
    """Ensure reasoning effort and max_tokens are mapped to the new schema."""
    completions = CompletionsBody(
        model="gpt-5-mini",
        messages=[
            {"role": "system", "content": "Act helpful"},
            {"role": "user", "content": "hi"},
        ],
        max_tokens=128,
        reasoning_effort="minimal",
    )

    responses = ResponsesBody.from_completions(completions)

    assert responses.max_output_tokens == 128
    assert responses.reasoning["effort"] == "minimal"  # type: ignore[index]
    assert responses.instructions == "Act helpful"


def test_responses_body_from_completions_converts_messages() -> None:
    """Validate that messages become the structured Responses API input."""
    messages = [
        {"role": "system", "content": "System prompt"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "hello"},
                {"type": "image_url", "image_url": {"url": "https://example.com/pic.png"}},
            ],
        },
        {"role": "assistant", "content": "intermediate result"},
    ]

    completions = CompletionsBody(
        model="gpt-4o",
        messages=messages,
    )

    responses = ResponsesBody.from_completions(completions)

    assert isinstance(responses.input, list)
    assert len(responses.input) == 2  # system message is removed

    user_block = responses.input[0]
    assert user_block["role"] == "user"
    block_types = [block["type"] for block in user_block["content"]]  # type: ignore[index]
    assert block_types == ["input_text", "input_image"]

    assistant_block = responses.input[1]
    assert assistant_block["role"] == "assistant"
    content = assistant_block["content"][0]  # type: ignore[index]
    assert content["type"] == "output_text"
    assert content["text"] == "intermediate result"
