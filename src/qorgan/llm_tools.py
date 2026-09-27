"""Small shared helpers for Gemini structured-JSON generation calls.

Used by both `classifier/llm_classifier.py` (scoring) and `data/generate.py` (synthetic
corpus generation) so the "call Gemini for a JSON payload and parse it" logic lives in
exactly one place.

The `client` is always injected by callers (a `google-genai`-style object exposing
`client.models.generate_content(...)`), so importing these modules never requires a
`GEMINI_API_KEY` and tests can pass a fake client with no network.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Any


# Per-request ceiling for build-time calls (ms): a hung connection must fail and be
# retried by the caller, not stall a 100-call batch (seen 2026-09-17 on the paraphrase run).
_HTTP_TIMEOUT_MS = 120_000

# Wall-clock deadline per call, independent of the transport. httpx's read timeout measures
# the gap *between bytes*, so a socket that stays ESTABLISHED while the server sends nothing
# never trips it: ADR D38 observed 40-minute hangs that way in the evaluation, and a real
# English generation run hung for 83 minutes at 0 % CPU with no output (ADR D53). The
# classifier had its own deadline; putting one here covers the generate and label CLIs too.
_CALL_DEADLINE_S = 180.0


class LLMResponseError(RuntimeError):
    """Raised when a Gemini response cannot be parsed into the expected JSON object."""


def build_client(api_key: str | None) -> Any:  # pragma: no cover - real network client
    """Construct a live `google-genai` client for CLI entry points.

    Kept out of module import paths (callers inject a client in tests/app code); only the
    generate/label CLIs, which genuinely need the network, call this.
    """
    if not api_key:
        raise LLMResponseError(
            "GEMINI_API_KEY (or GOOGLE_API_KEY) is not set; cannot build a live Gemini client. "
            "Add it to .env or the environment."
        )
    from google import genai
    from google.genai import types

    return genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=_HTTP_TIMEOUT_MS))


def thinking_budget_for(model: str) -> int:
    """Recommended `thinking_budget` (in tokens) for a structured-JSON call on `model`.

    Gemini 2.5 spends "thinking" tokens *inside* `max_output_tokens`, so an unbounded
    thinking budget silently truncates the JSON we actually need. For these
    extract/generate calls we don't want chain-of-thought: `flash` supports fully
    disabling it (`0`); `pro` cannot go below its floor, so we cap it low (`128`) and
    lean on token headroom instead.
    """
    return 0 if "flash" in model.lower() else 128


def generate_json(
    client: Any,
    *,
    model: str,
    prompt: str,
    response_schema: dict[str, Any] | None = None,
    system_instruction: str | None = None,
    max_output_tokens: int = 2048,
    thinking_budget: int | None = None,
    deadline_s: float | None = None,
) -> dict[str, Any]:
    """Call Gemini for structured JSON output and return the parsed object.

    Uses `response_mime_type="application/json"` (plus an optional `response_schema`) so the
    model is constrained to emit a single JSON object. Pass `thinking_budget` (see
    `thinking_budget_for`) to stop 2.5-series "thinking" tokens from eating the output
    budget and truncating the JSON. Raises `LLMResponseError` if the response carries no
    parseable JSON object.

    The call is abandoned after `deadline_s` wall-clock seconds (default `_CALL_DEADLINE_S`)
    and `TimeoutError` is raised: the transport timeout alone cannot end a silent socket. The
    worker thread is left to die with its socket -- it holds no state we keep.
    """
    config: dict[str, Any] = {
        "response_mime_type": "application/json",
        "max_output_tokens": max_output_tokens,
    }
    if system_instruction:
        config["system_instruction"] = system_instruction
    if response_schema is not None:
        config["response_schema"] = response_schema
    if thinking_budget is not None:
        config["thinking_config"] = {"thinking_budget": thinking_budget}

    limit = _CALL_DEADLINE_S if deadline_s is None else deadline_s
    # Not a `with` block: its __exit__ joins the worker, which is exactly the hang we are
    # escaping. A thread blocked in a socket read cannot be cancelled -- it is abandoned and
    # ends when its socket does, holding no state we keep.
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gemini-call")
    future = pool.submit(client.models.generate_content, model=model, contents=prompt, config=config)
    try:
        response = future.result(timeout=limit)
    except FutureTimeout as exc:
        pool.shutdown(wait=False, cancel_futures=True)
        raise TimeoutError(f"Gemini call exceeded the {limit:.0f} s deadline") from exc
    pool.shutdown(wait=False)
    return parse_json_response(response)


def parse_json_response(response: Any) -> dict[str, Any]:
    """Extract a JSON object from a Gemini response (prefers `.parsed`, falls back to `.text`)."""
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, dict):
        return parsed

    text = getattr(response, "text", None)
    if not text or not str(text).strip():
        raise LLMResponseError("Gemini response contained no JSON payload (empty .text/.parsed)")
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise LLMResponseError(f"Gemini response was not valid JSON: {text!r}") from exc
    if not isinstance(data, dict):
        raise LLMResponseError(f"Gemini JSON payload was not an object: {data!r}")
    return data
