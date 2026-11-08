"""Gemini provider on the google-genai 3.x SDK.

SDK notes that shape this code (verified against google-genai 3.0.0):
- No request timeout by default, so one is set. All retrying happens here, not in the SDK: the SDK's retry
  options would stack with ours, and the SDK never honours the server's RetryInfo on 429.
- Network errors surface as httpx2 exceptions, not APIError; some malformed responses raise ValueError
  subclasses. Every failure leaves this module as a ProviderError.
- Gemini 3.6+ / 4 ignore temperature, so it isn't sent; thinking_level is used instead.
"""

from __future__ import annotations

import json
import logging
import random
import time

import httpx2
from google import genai
from google.genai import errors, types

from .. import config
from .base import LLMResult, ProviderError

log = logging.getLogger(__name__)

_MAX_RATE_LIMIT_RETRIES = 6
# 503 "model overloaded" can last minutes; back off 10, 20, 40, 60s (jittered so parallel workers spread out).
_MAX_TRANSIENT_ATTEMPTS = 5
# A server asking us to wait longer than this is effectively out of quota: pause instead of sleeping.
_MAX_RETRY_DELAY_SEC = 90.0
# Upper bound on one generate_json call, retries included, so a stuck call can't hold a worker for long.
_CALL_DEADLINE_SEC = 20 * 60
_SDK_ERRORS = (errors.APIError, errors.UnknownApiResponseError, errors.ContinuationInterruptedError)


def _backoff(attempt: int) -> float:
    return min(60.0, 10.0 * 2 ** (attempt - 1)) * random.uniform(0.8, 1.2)


def _error_details(e: errors.APIError) -> list[dict]:
    body = e.details if isinstance(e.details, dict) else {}
    details = body.get("error", {}).get("details", []) if isinstance(body.get("error"), dict) else []
    return [d for d in details if isinstance(d, dict)] if isinstance(details, list) else []


def _retry_delay(e: errors.APIError) -> float | None:
    for d in _error_details(e):
        if str(d.get("@type", "")).endswith("google.rpc.RetryInfo"):
            try:
                return float(str(d.get("retryDelay", "")).rstrip("s"))
            except ValueError:
                return None
    return None


def _is_daily_quota(e: errors.APIError) -> bool:
    for d in _error_details(e):
        if str(d.get("@type", "")).endswith("google.rpc.QuotaFailure"):
            for violation in d.get("violations", []) if isinstance(d.get("violations"), list) else []:
                if isinstance(violation, dict) and "PerDay" in str(violation.get("quotaId", "")):
                    return True
    return False


def _has_reason(e: errors.APIError, reason: str) -> bool:
    return any(d.get("reason") == reason for d in _error_details(e))


def _client_error(e: errors.ClientError, model: str | None) -> ProviderError:
    if _has_reason(e, "API_KEY_INVALID") or (e.code == 400 and "API key" in str(e.message)):
        return ProviderError("The Gemini API key is invalid. Check it in Settings.", kind="auth")
    if e.code in (401, 403):
        return ProviderError(
            "This API key isn't allowed to call Gemini (permission denied). Check the key's project in AI Studio.",
            kind="auth",
        )
    if e.code == 404:
        return ProviderError(
            f"Model '{model}' isn't available for this API key. Pick another model in Settings.", kind="model"
        )
    if e.code == 429:
        return ProviderError("Gemini rate limit hit and retries ran out. Try again in a minute.", kind="quota")
    return ProviderError(f"Gemini rejected the request ({e.code} {e.status}): {e.message}")


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, client_args: dict | None = None):
        """client_args go to the underlying httpx2 client (tests pass a mock transport)."""
        if not api_key:
            raise ProviderError("No Gemini API key set. Add one in Settings.", kind="auth")
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=config.LLM_TIMEOUT_MS, client_args=client_args),
        )

    def close(self) -> None:
        self._client.close()

    def generate_json(self, *, model, system, messages, schema, thinking_level=None) -> LLMResult:
        contents = [types.Content(role=role, parts=[types.Part(text=text)]) for role, text in messages]
        cfg = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=schema,
            max_output_tokens=config.LLM_MAX_OUTPUT_TOKENS,
            thinking_config=types.ThinkingConfig(thinking_level=thinking_level) if thinking_level else None,
        )
        resp = self._call(model, contents, cfg)
        try:
            candidate = resp.candidates[0] if resp.candidates else None
            reason = candidate.finish_reason if candidate else None
            text = (resp.text or "") if candidate is not None else ""
        except Exception as exc:  # odd response shapes the SDK can't read
            raise ProviderError(f"Gemini returned a response that couldn't be read: {exc}") from exc
        if candidate is None or reason != types.FinishReason.STOP:
            raise ProviderError(
                f"Gemini returned no usable output (finish_reason={reason}, prompt_feedback={resp.prompt_feedback})."
            )
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"Gemini returned malformed JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ProviderError("Gemini returned JSON that isn't an object.")
        usage = {}
        if resp.usage_metadata:
            u = resp.usage_metadata
            usage = {
                "prompt_tokens": u.prompt_token_count,
                "output_tokens": u.candidates_token_count,
                "thinking_tokens": u.thoughts_token_count,
                "total_tokens": u.total_token_count,
            }
        return LLMResult(data=data, raw_text=text, usage=usage, model_version=resp.model_version)

    def _sleep_or_give_up(self, delay: float, deadline: float, why: str) -> None:
        if time.monotonic() + delay > deadline:
            raise ProviderError(f"Gave up on Gemini after repeated {why}; try again later.", kind="server")
        time.sleep(delay)

    def _call(self, model, contents, cfg):
        deadline = time.monotonic() + _CALL_DEADLINE_SEC
        rate_limited = transient = 0
        while True:
            try:
                return self._client.models.generate_content(model=model, contents=contents, config=cfg)
            except errors.ClientError as e:
                if e.code != 429:
                    raise _client_error(e, model) from e
                delay = _retry_delay(e)
                if _is_daily_quota(e) or (delay is not None and delay > _MAX_RETRY_DELAY_SEC):
                    raise ProviderError(
                        f"Gemini quota for {model} is used up for now. Try again later or switch model.", kind="quota"
                    ) from e
                rate_limited += 1
                if rate_limited > _MAX_RATE_LIMIT_RETRIES:
                    raise _client_error(e, model) from e
                delay = delay if delay is not None else min(60.0, 4.0 * 2 ** (rate_limited - 1))
                log.info("Gemini 429 on %s; retrying in %.1fs", model, delay)
                self._sleep_or_give_up(delay + 0.5, deadline, "rate limits")
            except errors.ServerError as e:
                transient += 1
                if transient >= _MAX_TRANSIENT_ATTEMPTS:
                    raise ProviderError(f"Gemini server error ({e.code} {e.status}). Try again later.", kind="server") from e
                self._sleep_or_give_up(_backoff(transient), deadline, "server errors")
            except httpx2.TransportError as e:
                transient += 1
                if transient >= _MAX_TRANSIENT_ATTEMPTS:
                    raise ProviderError(f"Couldn't reach Gemini: {type(e).__name__}: {e}", kind="network") from e
                self._sleep_or_give_up(_backoff(transient), deadline, "network errors")
            except httpx2.HTTPError as e:  # redirects, decoding errors: retrying won't help
                raise ProviderError(f"Unexpected response from Gemini: {type(e).__name__}: {e}", kind="network") from e
            except _SDK_ERRORS as e:
                raise ProviderError(f"Gemini error: {type(e).__name__}: {e}") from e

    def list_models(self) -> list[str]:
        try:
            ids = []
            for m in self._client.models.list(config={"page_size": 100}):
                if "generateContent" in (m.supported_actions or []):
                    ids.append((m.name or "").removeprefix("models/"))
            return ids
        except errors.ClientError as e:
            raise _client_error(e, None) from e
        except errors.ServerError as e:
            raise ProviderError(f"Gemini server error ({e.code}) while checking the key.", kind="server") from e
        except httpx2.HTTPError as e:
            raise ProviderError(f"Couldn't reach Gemini: {type(e).__name__}: {e}", kind="network") from e
        except _SDK_ERRORS as e:
            raise ProviderError(f"Gemini error while checking the key: {type(e).__name__}: {e}") from e
