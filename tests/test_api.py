"""Smoke tests for the thin HTTP API (`qorgan.api`) — mock backend, no network/keys."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from qorgan.api import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_health_reports_backend_and_threshold(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert 0.0 <= body["threshold"] <= 1.0


def test_analyze_scam_flags_with_grounded_evidence(client: TestClient) -> None:
    transcript = (
        "Это служба безопасности банка. Переведите деньги на безопасный счёт "
        "и никому не говорите, назовите код из сообщения."
    )
    res = client.post("/api/analyze", json={"transcript": transcript, "backend": "mock"})
    assert res.status_code == 200
    body = res.json()
    assert body["flagged"] is True
    assert body["risk"] >= body["threshold"]
    assert body["tags"], "a flagged verdict must carry tactic tags"
    for span in body["spans"]:  # evidence must be verbatim, in-bounds spans
        assert transcript[span["start"]:span["end"]] == span["text"]
    assert body["explanation"]["reason"]


def test_analyze_legit_call_stays_clear(client: TestClient) -> None:
    transcript = "Здравствуйте, ваша карта готова, можете забрать её в отделении банка."
    body = client.post(
        "/api/analyze", json={"transcript": transcript, "backend": "mock"}
    ).json()
    assert body["flagged"] is False


def test_analyze_kk_locale_renders_kk_explanation(client: TestClient) -> None:
    transcript = "Ақшаңызды қауіпсіз шотқа аударыңыз, ешкімге айтпаңыз."
    body = client.post(
        "/api/analyze", json={"transcript": transcript, "locale": "kk", "backend": "mock"}
    ).json()
    assert body["explanation"]["reason"]


def test_blank_transcript_rejected(client: TestClient) -> None:
    assert client.post("/api/analyze", json={"transcript": "   "}).status_code == 422


# --- QA 2026-09-29 -------------------------------------------------------------------------


def test_english_is_an_analyze_locale(client: TestClient) -> None:
    # ADR D52 made English a reviewed content locale; the citizen endpoint refused it with 422.
    res = client.post("/api/analyze", json={"transcript": "Назовите код из SMS", "backend": "mock", "locale": "en"})
    assert res.status_code == 200
    assert res.json()["explanation"]["reason"]


def test_an_unknown_backend_is_a_client_error_not_a_500(client: TestClient) -> None:
    res = client.post("/api/analyze", json={"transcript": "Алло", "backend": "nope"})
    assert res.status_code == 422
    assert "nope" not in res.text  # refusals name the problem, never echo the input
