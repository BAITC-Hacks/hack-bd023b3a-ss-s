"""Open demo access to the analyst console (`QORGAN_ADMIN_OPEN_ACCESS`, ADR D59).

For a public demo whose visitors (a jury) hold no key, the console can serve a keyless request
as the fixed identity `public-demo` with a configured role. It is off by default, and switching
it on changes only *who* may enter: every action is still audited under that identity, roles and
the investigator's stated purpose still apply, and a personal key keeps its own identity.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from qorgan.analysts import RESERVED_IDS
from qorgan.analytics.pipeline import write_organizations_jsonl
from qorgan.api import app
from qorgan.audit import load_audit
from qorgan.config import ConfigError, load_config
from qorgan.data.incident_seed import write_incidents_jsonl
from qorgan.data.schema import Incident, Label, Organization, TacticTag
from support.analysts import INVESTIGATOR_ID, as_investigator
from support.numbers import hashed, prefix

PUBLIC_ID = "public-demo"
WRONG_KEY = "not-an-analyst-key-0123456789abcdef"


@pytest.fixture()
def client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("QORGAN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("QORGAN_TAXONOMY_PATH", "data/taxonomy/tactics.yaml")
    processed = tmp_path / "processed"
    incident = Incident(
        id="i1", dialogue_id="i1", transcript="это служба безопасности банка, продиктуйте код из смс",
        label=Label(risk=0.9, tactic_tags=(TacticTag(id="otp_request"),)),
        number_hash=hashed("+7 700 101 20 30"), number_prefix=prefix("+7 700 101 20 30"),
    )
    write_organizations_jsonl([Organization(id="org_0", members=("i1",))], processed / "organizations.jsonl")
    write_incidents_jsonl([incident], processed / "incidents.jsonl")
    return TestClient(app)


def _audit(tmp_path):
    return load_audit(tmp_path / "processed" / "audit_log.jsonl")


def _open(client, headers=None):
    return client.post(
        "/api/admin/incidents/i1/open", params={"backend": "mock"},
        json={"purpose": "pattern_review"}, headers=headers or {},
    )


def test_off_by_default_a_keyless_request_is_refused(client) -> None:
    assert load_config().admin_open_access is None
    assert client.get("/api/admin/overview").status_code == 401


def test_an_unknown_value_is_a_config_error(monkeypatch) -> None:
    monkeypatch.setenv("QORGAN_ADMIN_OPEN_ACCESS", "admin")
    with pytest.raises(ConfigError):
        load_config()


def test_the_public_identity_is_reserved() -> None:
    assert PUBLIC_ID in RESERVED_IDS


def test_open_as_analyst_serves_the_console_without_a_key(client, monkeypatch) -> None:
    monkeypatch.setenv("QORGAN_ADMIN_OPEN_ACCESS", "analyst")
    session = client.get("/api/admin/session")
    assert session.status_code == 200
    assert session.json()["id"] == PUBLIC_ID
    assert session.json()["role"] == "analyst"
    assert session.json()["open_access"] is True
    assert client.get("/api/admin/overview").json()["available"] is True


def test_open_as_analyst_still_refuses_a_full_transcript(client, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QORGAN_ADMIN_OPEN_ACCESS", "analyst")
    assert _open(client).status_code == 403
    denied = [e for e in _audit(tmp_path) if e.action == "access.denied"]
    assert [e.actor_id for e in denied] == [PUBLIC_ID]


def test_open_as_investigator_opens_with_a_purpose_and_audits_it(client, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QORGAN_ADMIN_OPEN_ACCESS", "investigator")
    assert _open(client).status_code == 200
    opened = [e for e in _audit(tmp_path) if e.action == "case.open"]
    assert [(e.actor_id, e.purpose) for e in opened] == [(PUBLIC_ID, "pattern_review")]


def test_a_personal_key_keeps_its_own_identity(client, monkeypatch) -> None:
    monkeypatch.setenv("QORGAN_ADMIN_OPEN_ACCESS", "analyst")
    session = client.get("/api/admin/session", headers=as_investigator()).json()
    assert (session["id"], session["role"], session["open_access"]) == (INVESTIGATOR_ID, "investigator", True)


def test_a_wrong_key_is_still_refused(client, monkeypatch) -> None:
    monkeypatch.setenv("QORGAN_ADMIN_OPEN_ACCESS", "analyst")
    assert client.get("/api/admin/overview", headers={"X-Analyst-Key": WRONG_KEY}).status_code == 401


def test_open_access_needs_no_personal_keys_but_still_the_audit_key(client, monkeypatch) -> None:
    monkeypatch.setenv("QORGAN_ADMIN_OPEN_ACCESS", "analyst")
    monkeypatch.setenv("QORGAN_ANALYST_KEYS", "")
    assert client.get("/api/admin/overview").status_code == 200
    monkeypatch.setenv("QORGAN_AUDIT_CHAIN_KEY", "")
    assert client.get("/api/admin/overview").status_code == 503
