"""Order of the deploy bootstrap steps (`scripts/deploy_bootstrap.py`).

On a fresh clone the model probe, a fallback retrain and the Level-2 seeding all embed
text through the int8 ONNX graph under `site/models/`. The embedder must therefore be in
place before any of them runs -- otherwise a clean self-deploy (and the Docker build)
fails with ONNX `NO_SUCHFILE` even though every download succeeded.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "deploy_bootstrap.py"


def _load_bootstrap():
    spec = importlib.util.spec_from_file_location("deploy_bootstrap", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_embedder_is_provisioned_before_anything_embeds(monkeypatch):
    bootstrap = _load_bootstrap()
    calls: list[str] = []
    for step in ("ensure_corpus", "ensure_dialogue_pool", "ensure_embedder", "ensure_embed_runtime",
                 "ensure_model", "ensure_l2_seeds", "ensure_web_weights", "ensure_asr_models"):
        monkeypatch.setattr(bootstrap, step, lambda *args, step=step, **kwargs: calls.append(step))

    bootstrap.main()

    assert calls.index("ensure_embedder") < calls.index("ensure_model")
    assert calls.index("ensure_embedder") < calls.index("ensure_l2_seeds")
    # The browser's head weights are copied from the bundle, so only after it exists.
    assert calls.index("ensure_model") < calls.index("ensure_web_weights")


def test_corpus_tops_up_missing_splits_without_overwriting_local_ones(monkeypatch, tmp_path):
    bootstrap = _load_bootstrap()
    processed = tmp_path / "processed"
    processed.mkdir()
    (processed / "train.jsonl").write_text("local train\n", encoding="utf-8")  # e.g. rebuilt locally
    hub = tmp_path / "hub"
    hub.mkdir()
    for name in bootstrap.SPLIT_FILES:
        (hub / name).write_text(f"hub {name}\n", encoding="utf-8")
    monkeypatch.setattr(bootstrap, "PROCESSED", processed)
    import huggingface_hub

    monkeypatch.setattr(huggingface_hub, "snapshot_download", lambda *a, **k: str(hub))

    bootstrap.ensure_corpus()

    # The honest cross-generator split ships with every fresh setup (ADR D35).
    assert "shift.jsonl" in bootstrap.SPLIT_FILES
    assert (processed / "shift.jsonl").read_text(encoding="utf-8") == "hub shift.jsonl\n"
    assert (processed / "train.jsonl").read_text(encoding="utf-8") == "local train\n"


# --- the committed browser weights are the product (2026-09-29) -------------------------------
# A fresh clone downloads the Hub's sklearn bundle; after a lexicon change it is stale. The
# bootstrap used to retrain a *different* model from the local corpus and copy its export over
# the committed `site/models/weights.json`, silently shipping another model to every browser.


def _paths(bootstrap, monkeypatch, tmp_path):
    model_dir, site = tmp_path / "linear", tmp_path / "site_models"
    (model_dir / "web").mkdir(parents=True)
    site.mkdir()
    monkeypatch.setattr(bootstrap, "MODEL_DIR", model_dir)
    monkeypatch.setattr(bootstrap, "SITE_MODELS", site)
    return model_dir / "web" / "weights.json", site / "weights.json"


def test_committed_browser_weights_are_never_overwritten(monkeypatch, tmp_path):
    bootstrap = _load_bootstrap()
    exported, committed = _paths(bootstrap, monkeypatch, tmp_path)
    exported.write_text('{"from": "bundle"}', encoding="utf-8")
    committed.write_text('{"from": "git"}', encoding="utf-8")
    monkeypatch.setattr(bootstrap, "_web_weights_usable", lambda path: True)

    bootstrap.ensure_web_weights("bundle")

    assert committed.read_text(encoding="utf-8") == '{"from": "git"}'


def test_missing_or_unusable_browser_weights_come_from_a_valid_bundle(monkeypatch, tmp_path):
    bootstrap = _load_bootstrap()
    exported, committed = _paths(bootstrap, monkeypatch, tmp_path)
    exported.write_text('{"from": "bundle"}', encoding="utf-8")

    bootstrap.ensure_web_weights("bundle")  # missing -> copied
    assert committed.read_text(encoding="utf-8") == '{"from": "bundle"}'

    committed.write_text('{"broken": true}', encoding="utf-8")
    monkeypatch.setattr(bootstrap, "_web_weights_usable", lambda path: False)
    bootstrap.ensure_web_weights("retrained")  # unusable -> replaced by the fresh export
    assert committed.read_text(encoding="utf-8") == '{"from": "bundle"}'


def test_a_stale_bundle_is_not_retrained_when_the_browser_weights_serve(monkeypatch, tmp_path):
    bootstrap = _load_bootstrap()
    _paths(bootstrap, monkeypatch, tmp_path)
    (bootstrap.MODEL_DIR / "metadata.json").write_text("{}", encoding="utf-8")  # no download
    ran: list[list[str]] = []
    monkeypatch.setattr(bootstrap, "_run", lambda args: ran.append(args))
    monkeypatch.setattr(bootstrap, "_linear_source", lambda: "web")

    assert bootstrap.ensure_model() == "web"
    assert ran == [], "no retrain: it would train a different model than the browser ships"


def test_level2_seeding_follows_the_configured_data_dir_and_key(monkeypatch, tmp_path):
    # The container mounts the env file at /app/.env: the key reaches the process through the
    # config loader, not necessarily as an environment variable, and the data dir is configured.
    bootstrap = _load_bootstrap()
    ran: list[list[str]] = []
    monkeypatch.setattr(bootstrap, "_run", lambda args: ran.append(args))
    monkeypatch.setenv("QORGAN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("QORGAN_NUMBER_HMAC_KEY", "tests-only-key")

    bootstrap.ensure_l2_seeds()
    assert ran, "no organizations in the configured data dir -> seed"

    ran.clear()
    (tmp_path / "processed").mkdir(exist_ok=True)
    (tmp_path / "processed" / "organizations.jsonl").write_text("", encoding="utf-8")
    bootstrap.ensure_l2_seeds()
    assert ran == [], "already seeded in the configured data dir"


_STEPS = ("ensure_corpus", "ensure_dialogue_pool", "ensure_embedder", "ensure_embed_runtime", "ensure_model",
          "ensure_l2_seeds", "ensure_web_weights", "ensure_asr_models")


def _record_steps(monkeypatch, bootstrap) -> list[str]:
    calls: list[str] = []
    for step in _STEPS:
        monkeypatch.setattr(bootstrap, step, lambda *args, step=step, **kwargs: calls.append(step))
    return calls


# The container must answer its health check within the platform's window (Railway: 5 min),
# but seeding Level 2 embeds ~500 transcripts -- minutes on a shared vCPU. The entrypoint runs
# the `serve` phase, starts `seeds` in the background and serves at once (ADR D60).
def test_serve_phase_provisions_everything_but_the_level2_seeds(monkeypatch):
    bootstrap = _load_bootstrap()
    calls = _record_steps(monkeypatch, bootstrap)
    bootstrap.main(["--phase", "serve"])
    assert "ensure_l2_seeds" not in calls
    assert set(calls) == set(_STEPS) - {"ensure_l2_seeds"}


def test_seeds_phase_only_seeds(monkeypatch):
    bootstrap = _load_bootstrap()
    calls = _record_steps(monkeypatch, bootstrap)
    bootstrap.main(["--phase", "seeds"])
    assert calls == ["ensure_l2_seeds"]


def test_default_phase_runs_every_step(monkeypatch):
    bootstrap = _load_bootstrap()
    calls = _record_steps(monkeypatch, bootstrap)
    bootstrap.main([])
    assert set(calls) == set(_STEPS)


def test_entrypoint_serves_before_the_seeds_finish() -> None:
    script = (_SCRIPT.parent / "deploy_entrypoint.sh").read_text(encoding="utf-8")
    serve = script.index("deploy_bootstrap.py --phase serve")
    seeds = script.index("deploy_bootstrap.py --phase seeds")
    assert serve < seeds < script.index("exec uvicorn")
    assert script[seeds:script.index("\n", seeds)].rstrip().endswith("&"), "seeding runs in the background"
