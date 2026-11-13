import json
from dataclasses import replace

import pytest

from lm15 import Config, DataPart, LMRouter, Message, OpenRouterDecisionsLM, ProviderError, Request, RouterConfig, UnsupportedFeatureError, judgments, yes_no
from lm15.types import document
from lm15.testing import FakeResponse, FakeTransport

REQUEST = Request(model="openrouter-decisions:google/gemini-decision-1-20261111", messages=(Message.user("Inspect"),),
                  config=Config(response_format=judgments(ok=yes_no("Is this complete?"))))
BODY = {"id": "test-decision", "model": "google/gemini-decision-1-20261111", "provider": "Google AI Studio",
        "answers": {"ok": {"type": "noul", "noul": 0.9, "confidence": 0.9}},
        "usage": {"input_tokens": 100, "output_tokens": 0, "cost": 0.00001}}


def transport(body=BODY):
    return FakeTransport([FakeResponse(status=200, body=json.dumps(body).encode())])


def test_router_pdf_wire_and_raw_billing_roundtrip():
    from lm15.serde import response_from_dict, response_to_dict
    wire = transport()
    request = replace(REQUEST, messages=(Message.user([DataPart(value={"note": "check"}), document(data=b"%PDF-1.4\nfixture", media_type="application/pdf")]),))
    result = LMRouter(RouterConfig(api_keys={"openrouter-decisions": "test"}, transport=wire)).complete(request)
    sent = wire.requests[0]
    assert sent.url == "https://openrouter.ai/api/alpha/decisions"
    payload = json.loads(sent.body)
    assert payload["model"] == "google/gemini-decision-1-20261111"
    assert payload["state"][1]["file"]["file_data"].startswith("data:application/pdf;base64,JVBER")
    assert result.data == {"ok": True}
    restored = response_from_dict(response_to_dict(result, include_provider_data=True))
    assert restored.provider_data["usage"]["cost"] == BODY["usage"]["cost"]
    assert restored.provider_data["decisions"]["answers"] == BODY["answers"]


def test_malformed_answer_keeps_billed_usage():
    body = {**BODY, "answers": {}}
    with pytest.raises(ProviderError) as caught:
        OpenRouterDecisionsLM(api_key="test", transport=transport(body)).complete(REQUEST)
    assert caught.value.partial.usage.input_tokens == 100
    assert caught.value.partial.finish_reason == "error"


def test_adaptations_are_visible_and_strict_is_opt_in():
    request = replace(REQUEST, config=replace(REQUEST.config, temperature=0.2))
    result = OpenRouterDecisionsLM(api_key="test", transport=transport()).complete(request)
    assert result.adaptations[0].field == "config.temperature"
    with pytest.raises(UnsupportedFeatureError):
        OpenRouterDecisionsLM(api_key="test", adaptations="refuse").plan(request)


def test_override_cannot_change_answer_space():
    request = replace(REQUEST, config=replace(REQUEST.config, extensions={"questions": {"ok": {"type": "choice"}}}))
    with pytest.raises(UnsupportedFeatureError, match="answer type"):
        OpenRouterDecisionsLM(api_key="test").plan(request)


@pytest.mark.asyncio
async def test_async_uses_same_codec():
    from lm15 import AsyncOpenRouterDecisionsLM
    from tests.test_router import FakeAsyncResponse, FakeAsyncTransport
    wire = FakeAsyncTransport([FakeAsyncResponse(200, json.dumps(BODY).encode())])
    result = await AsyncOpenRouterDecisionsLM(api_key="test", transport=wire).complete(REQUEST)
    assert result.data == {"ok": True}
