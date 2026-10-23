"""Billed usage survives nonstream output conversion failures, not as success."""

import asyncio
import json

import pytest

from lm15 import Message, OpenAIChatLM, OpenAILM, ProviderError, Request, Usage
from lm15.providers.async_base import AsyncOpenAIChatLM, AsyncOpenAILM
from lm15.providers.common import with_partial_usage
from lm15.providers.openai_chat import response_from_openai_chat
from lm15.testing import FakeResponse, FakeTransport
from tests.test_auxiliary_retry_after import AsyncTransport


REQUEST = Request(model="requested-model", messages=(Message.user("hello"),))


def body(dialect, *, named=False):
    data = {"id": "response-1", "model": "returned-model"}
    function = {"arguments": "{}"}
    if named:
        function["name"] = "lookup"
    if dialect == "chat":
        data.update(
            choices=[{"message": {"role": "assistant", "content": "hello", "tool_calls": [
                {"id": "call-1", "type": "function", "function": function},
            ]}, "finish_reason": "tool_calls"}],
            usage={"prompt_tokens": 15, "completion_tokens": 7, "total_tokens": 22,
                   "prompt_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 2, "audio_tokens": 3},
                   "completion_tokens_details": {"reasoning_tokens": 4, "audio_tokens": 2}},
        )
    else:
        data.update(
            status="completed",
            output=[{"type": "message", "content": [{"type": "output_text", "text": "hello"}]},
                    {"type": "function_call", "call_id": "call-1", **function}],
            usage={"input_tokens": 15, "output_tokens": 7, "total_tokens": 22,
                   "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 2, "audio_tokens": 3},
                   "output_tokens_details": {"reasoning_tokens": 4, "audio_tokens": 2}},
        )
    return data


def complete(data, dialect, asynchronous, *, status=200):
    response = FakeResponse(
        status=status, body=json.dumps(data).encode(),
        headers=[("X-Request-ID", "request-1"), ("Retry-After", "3")],
    )
    transport = AsyncTransport([response]) if asynchronous else FakeTransport([response])
    classes = {"chat": (OpenAIChatLM, AsyncOpenAIChatLM), "responses": (OpenAILM, AsyncOpenAILM)}
    client = classes[dialect][asynchronous](api_key="fake", transport=transport)
    try:
        return asyncio.run(client.complete(REQUEST)) if asynchronous else client.complete(REQUEST)
    finally:
        assert len(transport.requests) == 1  # Never retry a malformed billed reply.


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("dialect", ["chat", "responses"])
@pytest.mark.parametrize("total", [22, 99, None])
def test_unnamed_tool_call_keeps_billed_usage(dialect, asynchronous, total):
    data = body(dialect)
    if total is None:
        del data["usage"]["total_tokens"]
    else:
        data["usage"]["total_tokens"] = total
    with pytest.raises(ProviderError, match="tool call with no name") as caught:
        complete(data, dialect, asynchronous)
    error = caught.value
    assert type(error) is ProviderError
    assert error.code == "provider"
    assert error.request_id == "request-1"
    assert error.retry_after == 3.0
    partial = error.partial
    assert partial.id == "response-1"
    assert partial.model == "returned-model"
    assert partial.finish_reason == "error"
    assert not partial.text and not partial.tool_calls
    assert partial.usage == Usage(
        input_tokens=None if total == 99 else 15, output_tokens=None if total == 99 else 7,
        total_tokens=22 if total is None else total,
        cache_read_tokens=0, cache_write_tokens=2, reasoning_tokens=4,
        input_audio_tokens=3, output_audio_tokens=2,
    )


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("dialect", ["chat", "responses"])
@pytest.mark.parametrize("usage", [None, "bad", [], {"total_tokens": -1}, {"total_tokens": "bad"}])
def test_unusable_usage_never_masks_original_error(dialect, asynchronous, usage):
    data = body(dialect)
    data["usage"] = usage
    with pytest.raises(ProviderError, match="tool call with no name") as caught:
        complete(data, dialect, asynchronous)
    assert type(caught.value) is ProviderError
    assert caught.value.partial is None
    assert caught.value.request_id == "request-1"


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("dialect", ["chat", "responses"])
@pytest.mark.parametrize("usage", [{}, {"total_tokens": 0}, {"total_tokens": 22},
                                   {"prompt_tokens_details": [1], "input_tokens_details": [1]}])
def test_unknown_dimensions_stay_unknown(dialect, asynchronous, usage):
    data = body(dialect)
    del data["model"]  # The request model is the fallback, not a guessed identity.
    data["usage"] = usage
    with pytest.raises(ProviderError) as caught:
        complete(data, dialect, asynchronous)
    assert caught.value.partial.model == REQUEST.model
    assert caught.value.partial.usage == Usage(total_tokens=usage.get("total_tokens"))


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("dialect", ["chat", "responses"])
def test_successful_output_is_unchanged(dialect, asynchronous):
    data = body(dialect, named=True)
    response = complete(data, dialect, asynchronous)
    assert response.text is None  # Mixed text/tool messages have no text shortcut.
    assert response.message.parts[0].text == "hello"
    assert response.tool_calls[0].name == "lookup"
    assert response.tool_calls[0].input == {}
    assert response.finish_reason == "tool_call"
    assert response.provider_data == data
    assert response.usage.total_tokens == 22


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("dialect", ["chat", "responses"])
@pytest.mark.parametrize("status", [200, 400])
def test_error_envelope_retains_class_and_metadata(dialect, asynchronous, status):
    from lm15 import InvalidRequestError, ServerError

    data = body(dialect)
    data["error"] = {"code": "invalid_request_error", "message": "original failure"}
    expected = ServerError if status == 200 else InvalidRequestError
    with pytest.raises(expected, match="original failure") as caught:
        complete(data, dialect, asynchronous, status=status)
    assert type(caught.value) is expected
    assert caught.value.provider_code == "invalid_request_error"
    assert caught.value.request_id == "request-1"
    if status == 200:
        assert caught.value.partial.usage.total_tokens == 22
    else:
        assert caught.value.status == 400
        assert caught.value.partial is None  # HTTP errors still use normalize_error.


def test_chat_dict_reader_uses_the_same_partial_contract():
    with pytest.raises(ProviderError) as caught:
        response_from_openai_chat(body("chat"))
    error = caught.value
    partial = error.partial
    assert partial.usage.total_tokens == 22
    # Enriching diagnostics must preserve an existing partial and exception.
    assert with_partial_usage(error, body("chat"), model=None, parse_usage=lambda _: Usage()) is error
    assert error.partial is partial


def test_partial_usage_keeps_separate_reasoning_policy():
    from lm15.compat import OpenAIChatCompat

    data = body("chat")
    data["usage"]["total_tokens"] = 26
    client = OpenAIChatLM(api_key="fake", compat=OpenAIChatCompat(reasoning_usage="separate"))
    with pytest.raises(ProviderError) as caught:
        client.response_from_openai_chat(data)
    assert caught.value.partial.usage.input_tokens == 15
    assert caught.value.partial.usage.output_tokens == 11
    assert caught.value.partial.usage.total_tokens == 26
