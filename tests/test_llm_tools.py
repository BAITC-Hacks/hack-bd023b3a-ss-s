"""The shared Gemini seam (`qorgan.llm_tools`), including the wall-clock deadline.

ADR D38 hardened the *classifier's* client against a socket that stays ESTABLISHED while no
bytes arrive -- httpx's read timeout is the gap between bytes, so it never fires. The
generation and labelling CLIs go through the same `generate_json` and did not get that
protection: a real run hung for 83 minutes at 0 % CPU with no output (ADR D53).
"""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

from qorgan.llm_tools import LLMResponseError, generate_json


class _Blocking:
    """A client whose call never returns within the test's patience."""

    def __init__(self, seconds: float = 30.0) -> None:
        self.models = SimpleNamespace(generate_content=self._hang)
        self._seconds = seconds

    def _hang(self, **_kwargs):
        time.sleep(self._seconds)
        raise AssertionError("the deadline should have fired first")


class _Instant:
    def __init__(self, payload: dict) -> None:
        self.models = SimpleNamespace(
            generate_content=lambda **_k: SimpleNamespace(text=json.dumps(payload), parsed=None)
        )


def test_generate_json_gives_up_on_a_socket_that_never_answers():
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        generate_json(_Blocking(), model="m", prompt="p", deadline_s=0.25)
    assert time.monotonic() - started < 10, "the deadline must not wait for the transport"


def test_generate_json_returns_normally_well_inside_the_deadline():
    payload = {"utterances": [{"speaker": "caller", "text": "hi"}], "trigger_phrases": []}
    assert generate_json(_Instant(payload), model="m", prompt="p", deadline_s=30) == payload


def test_generate_json_still_reports_unparseable_output_as_an_llm_error():
    bad = SimpleNamespace(models=SimpleNamespace(
        generate_content=lambda **_k: SimpleNamespace(text="not json", parsed=None)))
    with pytest.raises(LLMResponseError):
        generate_json(bad, model="m", prompt="p", deadline_s=30)
