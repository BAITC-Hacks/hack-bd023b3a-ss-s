"""The server can score with the exact weights the browser ships (`site/models/weights.json`).

Found 2026-09-29: after a lexicon change (D51/D54) the committed browser weights were current
but `models/linear` (the sklearn bundle, gitignored, fetched from the Hub) was not -- so the
server failed its lexicon-hash check and silently degraded to the keyword `mock` (a textbook
«код из СМС» call scored 0.05), and the deploy bootstrap retrained a *different* model and
copied it over the committed browser weights. `load_linear_from_web` rebuilds a `LinearBundle`
from the JSON (the numpy `WebScorer` + the lexicon content embedded in it), and
`QORGAN_LINEAR_WEIGHTS` picks the source: `bundle`, `web`, or `auto` (bundle when it is valid
for the current lexicons, else the committed browser weights).
"""

from __future__ import annotations

import json
import shutil

import numpy as np
import pytest

from qorgan.classifier import predict
from qorgan.classifier.features import compute_feature_blocks, hybrid_matrix
from qorgan.classifier.linear_train import LinearFeatureMismatchError, train_and_export, train_linear
from qorgan.classifier.web_bundle import WEB_BUNDLE_FILENAME, export_web_bundle, load_linear_from_web
from qorgan.data.schema import Dialogue, Label, TacticTag, Utterance, spans_from_phrases

_LABEL_SPACE = ("otp_request", "urgency", "safe_account")
_THRESHOLDS = {"risk": 0.59, "enter": 0.59, "exit": 0.49}
_TEXTS = [
    "Продиктуйте код из SMS сейчас",
    "Как дела на выходных",
    "Код называть не нужно, это служба банка",
    "Переведите деньги на безопасный счёт, никому не говорите",
]


def _d(did, text, *, risk, tags=(), phrases=()):
    return Dialogue(
        id=did, language="ru", utterances=(Utterance(speaker="caller", text=text),),
        label=Label(risk=risk, tactic_tags=tuple(TacticTag(id=t) for t in tags), trigger_spans=spans_from_phrases(phrases, text)),
    )


def _corpus():
    scams = [_d(f"s{i}", f"Продиктуйте код из SMS номер {i}", risk=0.9, tags=["otp_request", "urgency"], phrases=["код из SMS"]) for i in range(10)]
    legit = [_d(f"n{i}", f"Обычный разговор про погоду {i}", risk=0.03) for i in range(10)]
    return scams + legit


@pytest.fixture()
def hybrid_bundle(fake_embedder):
    return train_linear(_corpus(), label_space=_LABEL_SPACE, embedder=fake_embedder, hard_signal=True)


@pytest.fixture()
def web_json(hybrid_bundle, tmp_path):
    path = tmp_path / WEB_BUNDLE_FILENAME
    path.write_text(json.dumps(export_web_bundle(hybrid_bundle, thresholds=_THRESHOLDS), ensure_ascii=False), encoding="utf-8")
    return path


# --- the loader ------------------------------------------------------------------------------


def test_web_weights_rebuild_a_bundle_that_scores_like_the_trained_one(hybrid_bundle, web_json, fake_embedder):
    served = load_linear_from_web(web_json)
    assert served.label_space == hybrid_bundle.label_space and served.hard_signal_enabled
    assert served.tactic_thresholds == hybrid_bundle.tactic_thresholds
    assert served.lexicon.entries == hybrid_bundle.lexicon.entries
    assert served.cue_lexicon_hash == hybrid_bundle.cue_lexicon_hash

    blocks = compute_feature_blocks(_TEXTS, embedder=fake_embedder, lexicon=served.lexicon,
                                    reassurance_patterns=served.reassurance_patterns)
    # Same tolerance as the WebScorer-vs-sklearn parity tests (float rounding, ~1e-8 here).
    np.testing.assert_allclose(served.risk_clf.predict_proba(hybrid_matrix(blocks))[:, 1],
                               hybrid_bundle.risk_clf.predict_proba(hybrid_matrix(blocks))[:, 1], rtol=0, atol=1e-6)
    np.testing.assert_allclose(served.tactic_clf.predict_proba(blocks.embedding),
                               hybrid_bundle.tactic_clf.predict_proba(blocks.embedding), rtol=0, atol=1e-6)

    for text in _TEXTS:  # the whole server verdict, not just the heads
        a = predict._linear_score(text, bundle=hybrid_bundle, embedder=fake_embedder)
        b = predict._linear_score(text, bundle=served, embedder=fake_embedder)
        assert b.risk == pytest.approx(a.risk, abs=1e-6)
        assert [t.id for t in b.tags] == [t.id for t in a.tags]
        assert [s.text for s in b.attributions] == [s.text for s in a.attributions]


def test_a_lexicon_that_does_not_match_its_own_hash_is_refused(web_json):
    data = json.loads(web_json.read_text(encoding="utf-8"))
    data["lexicon"]["cues"]["otp_request"].append("совсем новая фраза")
    web_json.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(LinearFeatureMismatchError, match="lexicon"):
        load_linear_from_web(web_json)


def test_weights_from_another_cue_matcher_are_refused(web_json):
    data = json.loads(web_json.read_text(encoding="utf-8"))
    data["cue_matcher_version"] = 999
    web_json.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(LinearFeatureMismatchError, match="matcher"):
        load_linear_from_web(web_json)


# --- which weights the server serves ---------------------------------------------------------


@pytest.fixture()
def sources(tmp_path, monkeypatch, fake_embedder):
    """A valid trained bundle dir and a copy of its browser export at a separate path."""
    bundle_dir = tmp_path / "linear"
    train_and_export(_corpus(), label_space=_LABEL_SPACE, out_dir=bundle_dir, embedder=fake_embedder, hard_signal=True)
    web = tmp_path / "site_weights.json"
    shutil.copyfile(bundle_dir / "web" / WEB_BUNDLE_FILENAME, web)
    monkeypatch.setenv("QORGAN_LINEAR_MODEL_DIR", str(bundle_dir))
    monkeypatch.setenv("QORGAN_WEB_WEIGHTS_PATH", str(web))
    predict._LINEAR_BUNDLE_CACHE.clear()
    yield bundle_dir, web
    predict._LINEAR_BUNDLE_CACHE.clear()


def _stale(bundle_dir):
    meta = json.loads((bundle_dir / "metadata.json").read_text(encoding="utf-8"))
    meta["cue_lexicon_hash"] = "0" * 64  # trained under a lexicon the repo no longer has
    (bundle_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")


def test_auto_serves_a_valid_bundle(sources):
    assert predict.linear_model_source() == "bundle"


def test_auto_serves_the_browser_weights_when_the_bundle_is_stale(sources):
    _stale(sources[0])
    assert predict.linear_model_source() == "web"
    assert predict._get_linear_bundle().hard_signal_enabled


def test_auto_serves_the_browser_weights_when_there_is_no_bundle(sources):
    shutil.rmtree(sources[0])
    assert predict.linear_model_source() == "web"


def test_web_policy_ignores_even_a_valid_bundle(sources, monkeypatch):
    monkeypatch.setenv("QORGAN_LINEAR_WEIGHTS", "web")
    assert predict.linear_model_source() == "web"


def test_bundle_policy_never_falls_back(sources, monkeypatch):
    monkeypatch.setenv("QORGAN_LINEAR_WEIGHTS", "bundle")
    _stale(sources[0])
    with pytest.raises(LinearFeatureMismatchError):
        predict.linear_model_source()


def test_nothing_usable_means_no_linear_model(sources):
    _stale(sources[0])
    sources[1].unlink()
    with pytest.raises(LinearFeatureMismatchError):
        predict.linear_model_source()


def test_an_unknown_policy_is_a_config_error(monkeypatch):
    from qorgan.config import ConfigError, load_config

    monkeypatch.setenv("QORGAN_LINEAR_WEIGHTS", "sometimes")
    with pytest.raises(ConfigError):
        load_config()


def test_health_says_which_weights_the_server_scores_with(sources, monkeypatch):
    from fastapi.testclient import TestClient

    from qorgan.api import app

    monkeypatch.setenv("QORGAN_CLASSIFIER_BACKEND", "linear")
    _stale(sources[0])
    assert TestClient(app).get("/api/health").json()["linear_model_source"] == "web"


def test_auto_serves_the_browser_weights_when_the_bundle_cannot_be_unpickled(sources):
    (sources[0] / "risk_clf.joblib").write_bytes(b"not a pickle")
    assert predict.linear_model_source() == "web"
