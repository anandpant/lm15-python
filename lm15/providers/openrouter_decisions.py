"""OpenRouter's typed Decisions endpoint; shared judgments, provider-specific media.

https://openrouter.ai/docs/guides/community/multimodal-decisions
The endpoint validates each model's media and question capabilities. It is not
the OpenRouter chat endpoint, and unsupported requests never fall back to chat.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, fields, replace
from typing import ClassVar

from ..access import OPENROUTER_DECISIONS_API
from ..adaptation import adapt, check_policy
from ..errors import ProviderError, map_http_error
from ..features import ProviderManifest
from ..judgments import request_judgments
from ..types import Config, DataPart, DocumentPart, ImagePart, TextPart
from .common import media_base64, usage_from_responses, with_partial_usage
from .typesafe import TypeSafeLM


@dataclass
class OpenRouterDecisionsLM(TypeSafeLM):
    base_url: str = "https://openrouter.ai/api/alpha"
    provider: str = field(default="openrouter-decisions", init=False)
    manifest: ClassVar[ProviderManifest] = OPENROUTER_DECISIONS_API

    def __post_init__(self):
        check_policy(self.adaptations)
        self._bind_access(self.access, credentials_path=self.credentials_path,
                          default_base_url="https://openrouter.ai/api/alpha", settings=self.settings)

    def _state(self, request):
        if request.system or len(request.messages) != 1 or request.messages[0].role != "user":
            raise self._refuse("messages", "MAP-13(b): decisions require one shared user input; conversation semantics would be lost")
        parts = request.messages[0].parts
        if len(parts) == 1 and isinstance(parts[0], DataPart):
            return parts[0].value
        state = []
        for index, part in enumerate(parts):
            if isinstance(part, TextPart):
                state.append(part.text)
            elif isinstance(part, DataPart):
                state.append(json.dumps(part.value, ensure_ascii=False, allow_nan=False))
            elif isinstance(part, (ImagePart, DocumentPart)):
                if part.file_id is not None:
                    raise self._refuse(f"messages[0].parts[{index}]", "MAP-13(b): provider file IDs are not portable; use inline bytes or HTTPS")
                if part.url is not None and not part.url.startswith("https://"):
                    raise self._refuse(f"messages[0].parts[{index}]", "MAP-13(d): remote media requires HTTPS")
                url = part.url or f"data:{part.media_type};base64,{media_base64(part)}"
                state.append({"type": "image_url", "image_url": {"url": url}} if isinstance(part, ImagePart)
                             else {"type": "file", "file": {"file_data": url}})
            else:
                raise self._refuse(f"messages[0].parts[{index}]", "MAP-13(b): this adapter supports text, data, images and documents only")
        return state

    def _questions(self, request):
        questions = super()._questions(request)
        overrides = (request.config.extensions or {}).get("questions", {})
        if not isinstance(overrides, dict) or overrides.keys() - questions.keys():
            raise self._refuse("config.extensions.questions", "MAP-13(b): overrides must name declared judgments")
        for name, override in overrides.items():
            if not isinstance(override, dict) or override.keys() - {"type", "instructions", "criteria"}:
                raise self._refuse("config.extensions.questions", "MAP-13(b): invalid question override")
            original = questions[name]
            if override.get("type", original["type"]) != original["type"]:
                raise self._refuse("config.extensions.questions", "MAP-13(b): override changes the declared answer type")
            criteria = override.get("criteria", original.get("criteria"))
            if original["type"] == "choice" and (not isinstance(criteria, dict) or set(criteria) != set(original["criteria"])):
                raise self._refuse("config.extensions.questions", "MAP-13(b): choice keys must match the declaration")
            if original["type"] == "score" and (not isinstance(criteria, list) or len(criteria) != len(original["criteria"])):
                raise self._refuse("config.extensions.questions", "MAP-13(b): score levels must match the declaration")
            questions[name] = {**original, **override}
        return questions

    def build_request(self, request, stream):
        request = self._wire_request(request)
        if stream or request.tools:
            raise self._refuse("stream" if stream else "tools", "MAP-13(b): decisions return one answer set and cannot execute tools")
        defaults = Config()
        for item in fields(request.config):
            name = item.name
            value = getattr(request.config, name)
            if name in {"response_format", "extensions", "probabilities"} or value == getattr(defaults, name):
                continue
            if name in {"temperature", "top_p", "top_k", "seed", "frequency_penalty", "presence_penalty"}:
                adapt(f"config.{name}", "dropped", "decisions score fixed alternatives instead of sampling text", asked=value, provider=self.provider)
            else:
                raise self._refuse(f"config.{name}", "MAP-13(d): this control cannot be safely inferred on the Decisions endpoint")
        extra = (request.config.extensions or {}).keys() - {"questions"}
        if extra:
            raise self._refuse("config.extensions", f"MAP-13(a): unsupported controls require an explicit mapping: {sorted(extra)}")
        return self._emit(method="POST", url=self.base_url.rstrip("/") + "/decisions",
                          endpoint="decisions", model=request.model, headers={"Content-Type": "application/json"},
                          payload={"model": request.model, "state": self._state(request), "questions": self._questions(request)})

    def parse_response(self, request, response):
        data = response.json()
        try:
            parsed = super().parse_response(request, response)
            # TypeSafe and OpenRouter share the judgment answer shape, not
            # authentication, media encoding or provider metadata.
            answers = parsed.provider_data["typesafe"]["answers"]
            for name, judgment in request_judgments(request).items():
                confidence = answers[name].get("confidence")
                if confidence is not None and (isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1):
                    raise ProviderError(f"Malformed confidence for {name}", provider=self.provider)
            return replace(parsed, id=data.get("id") or parsed.id,
                           usage=usage_from_responses(data.get("usage")),
                           provider_data={**data, "decisions": {"answers": answers, "refusals": []}})
        except ProviderError as error:
            if isinstance(data, dict):
                with_partial_usage(error, data, model=request.model, parse_usage=usage_from_responses)
            raise

    def normalize_error(self, status, body):
        message = f"HTTP {status}"
        try:
            detail = json.loads(body).get("error", {})
            message = detail.get("message", message)
        except (ValueError, AttributeError):
            pass
        return map_http_error(status, message, provider=self.provider, env_keys=self.access.env_keys)
