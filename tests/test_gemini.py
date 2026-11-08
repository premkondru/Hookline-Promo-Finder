"""GeminiProvider against a mocked HTTP transport: request shape, parsing and error handling, no network."""

import json

import httpx2
import pytest

from app.llm import ProviderError
from app.llm import gemini as gemini_module
from app.llm.gemini import GeminiProvider

KEY = "AIzaSyTESTKEY-0123456789abcdef"


def ok_body(text: str, finish: str = "STOP") -> dict:
    return {
        "candidates": [{"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": finish, "index": 0}],
        "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 30, "thoughtsTokenCount": 50,
                          "totalTokenCount": 200},
        "modelVersion": "gemini-3.8-flash-001",
    }


def error_body(code: int, status: str, details: list) -> dict:
    return {"error": {"code": code, "message": "boom", "status": status, "details": details}}


class Recorder:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        status, body = self.responses.pop(0)
        return httpx2.Response(status, json=body)


def provider(recorder) -> GeminiProvider:
    return GeminiProvider(KEY, client_args={"transport": httpx2.MockTransport(recorder)})


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    sleeps = []
    monkeypatch.setattr(gemini_module.time, "sleep", sleeps.append)
    return sleeps


SCHEMA = {"type": "object", "properties": {"candidates": {"type": "array"}}, "required": ["candidates"]}


def test_request_shape_and_parsing():
    rec = Recorder((200, ok_body('{"candidates": []}')))
    result = provider(rec).generate_json(
        model="gemini-3.8-flash", system="SYS", messages=[("user", "hello")], schema=SCHEMA, thinking_level="high"
    )
    assert result.data == {"candidates": []}
    assert result.usage == {"prompt_tokens": 120, "output_tokens": 30, "thinking_tokens": 50, "total_tokens": 200}
    req = rec.requests[0]
    assert req.url.path.endswith("/models/gemini-3.8-flash:generateContent")
    assert req.headers["x-goog-api-key"] == KEY
    body = json.loads(req.content)
    assert body["systemInstruction"]["parts"][0]["text"] == "SYS"
    assert body["contents"] == [{"role": "user", "parts": [{"text": "hello"}]}]
    cfg = body["generationConfig"]
    assert cfg["responseMimeType"] == "application/json"
    assert cfg["responseJsonSchema"] == SCHEMA
    thinking = cfg["thinkingConfig"]  # the SDK sends the proto field name; the API accepts either spelling
    assert (thinking.get("thinkingLevel") or thinking.get("thinking_level")).lower() == "high"
    assert "temperature" not in cfg  # ignored by Gemini 3.6+/4, so never sent


def test_rate_limit_honours_retry_info(no_sleep):
    retry = [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "37s"}]
    rec = Recorder((429, error_body(429, "RESOURCE_EXHAUSTED", retry)), (200, ok_body('{"candidates": []}')))
    provider(rec).generate_json(model="m", system="s", messages=[("user", "x")], schema=SCHEMA)
    assert len(rec.requests) == 2
    assert no_sleep == [37.5]


def test_daily_quota_fails_fast_and_pauses_queue():
    quota = [{"@type": "type.googleapis.com/google.rpc.QuotaFailure",
              "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]
    rec = Recorder((429, error_body(429, "RESOURCE_EXHAUSTED", quota)))
    with pytest.raises(ProviderError) as exc:
        provider(rec).generate_json(model="m", system="s", messages=[("user", "x")], schema=SCHEMA)
    assert exc.value.kind == "quota" and exc.value.pauses_queue
    assert len(rec.requests) == 1


def test_invalid_key_is_an_auth_error():
    info = [{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "API_KEY_INVALID"}]
    rec = Recorder((400, error_body(400, "INVALID_ARGUMENT", info)))
    with pytest.raises(ProviderError) as exc:
        provider(rec).generate_json(model="m", system="s", messages=[("user", "x")], schema=SCHEMA)
    assert exc.value.kind == "auth" and "invalid" in str(exc.value)


def test_truncated_output_is_rejected():
    rec = Recorder((200, ok_body('{"candid', finish="MAX_TOKENS")))
    with pytest.raises(ProviderError, match="finish_reason"):
        provider(rec).generate_json(model="m", system="s", messages=[("user", "x")], schema=SCHEMA)


def test_long_server_retry_delay_is_treated_as_quota(no_sleep):
    retry = [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "3600s"}]
    rec = Recorder((429, error_body(429, "RESOURCE_EXHAUSTED", retry)))
    with pytest.raises(ProviderError) as exc:
        provider(rec).generate_json(model="m", system="s", messages=[("user", "x")], schema=SCHEMA)
    assert exc.value.kind == "quota" and no_sleep == []


def test_server_errors_get_a_bounded_number_of_attempts(no_sleep):
    rec = Recorder(*[(503, error_body(503, "UNAVAILABLE", []))] * 8)
    with pytest.raises(ProviderError) as exc:
        provider(rec).generate_json(model="m", system="s", messages=[("user", "x")], schema=SCHEMA)
    assert exc.value.kind == "server"
    assert len(rec.requests) == 5  # no SDK retries stacked on top
    for wait, base in zip(no_sleep, [10, 20, 40, 60]):  # jittered exponential backoff
        assert 0.8 * base <= wait <= 1.2 * base


def test_unavailable_model_pauses_the_queue():
    rec = Recorder((404, error_body(404, "NOT_FOUND", [])))
    with pytest.raises(ProviderError) as exc:
        provider(rec).generate_json(model="gemini-x", system="s", messages=[("user", "x")], schema=SCHEMA)
    assert exc.value.kind == "model" and exc.value.pauses_queue


def test_list_models_keeps_generate_content_models():
    rec = Recorder((200, {"models": [
        {"name": "models/gemini-3.8-flash", "supportedGenerationMethods": ["generateContent", "countTokens"]},
        {"name": "models/gemini-embedding-001", "supportedGenerationMethods": ["embedContent"]},
    ]}))
    assert provider(rec).list_models() == ["gemini-3.8-flash"]
