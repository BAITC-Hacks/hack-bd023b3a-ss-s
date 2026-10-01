"""The on-device embedder's runtime is self-hosted, pinned by hash (ADR D61).

`live.html` is cross-origin isolated (COOP/COEP `require-corp`, for threaded WASM). WebKit --
Safari and every iPhone browser -- refuses a module worker's cross-origin import under that
policy ("Refused to load ... worker because of Cross-Origin-Embedder-Policy"), so the worker's
transformers.js import from jsDelivr failed and the microphone could not start. The three
runtime files are now served from this site, byte-identical to the 3.8.1 release the parity
fixtures pin (ADR D32).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from qorgan.web.embed_runtime import (
    TRANSFORMERS_BASE_URL,
    TRANSFORMERS_FILES,
    TRANSFORMERS_VENDOR_SUBDIR,
    TRANSFORMERS_VERSION,
    ensure_embed_runtime,
)

REPO = Path(__file__).resolve().parents[2]
WORKER = REPO / "site" / "core" / "embed-worker.js"


def test_runtime_is_installed_only_with_the_pinned_hashes(tmp_path, monkeypatch) -> None:
    good = {name: b"payload-" + name.encode() for name in TRANSFORMERS_FILES}
    monkeypatch.setattr(
        "qorgan.web.embed_runtime.TRANSFORMERS_FILES", {n: hashlib.sha256(b).hexdigest() for n, b in good.items()}
    )
    urls: list[str] = []
    target = ensure_embed_runtime(tmp_path / "site", downloader=lambda url: urls.append(url) or good[url.rsplit("/", 1)[1]])
    assert target == tmp_path / "site" / TRANSFORMERS_VENDOR_SUBDIR
    assert {p.name: p.read_bytes() for p in target.iterdir()} == good
    assert all(u.startswith(TRANSFORMERS_BASE_URL) for u in urls)
    # Present with the right hash: nothing is fetched again.
    never = lambda url: (_ for _ in ()).throw(AssertionError("fetched"))  # noqa: E731
    assert ensure_embed_runtime(tmp_path / "site", downloader=never) == target
    # A tampered download is refused and nothing is written.
    with pytest.raises(RuntimeError):
        ensure_embed_runtime(tmp_path / "other", downloader=lambda url: b"tampered")
    assert not (tmp_path / "other" / "vendor").exists()


def test_pinned_files_are_the_release_the_parity_fixtures_use() -> None:
    assert TRANSFORMERS_VERSION == "3.8.1"  # ADR D32: moves only together with onnxruntime
    assert set(TRANSFORMERS_FILES) == {
        "transformers.min.js", "ort-wasm-simd-threaded.jsep.mjs", "ort-wasm-simd-threaded.jsep.wasm",
    }
    dist = REPO / "node_modules" / "@huggingface" / "transformers" / "dist"
    if not dist.is_dir():
        pytest.skip("node_modules not installed")
    for name, expected in TRANSFORMERS_FILES.items():
        assert hashlib.sha256((dist / name).read_bytes()).hexdigest() == expected, name


def test_the_worker_loads_nothing_cross_origin() -> None:
    source = WORKER.read_text(encoding="utf-8")
    code = re.sub(r"//[^\n]*|/\*[\s\S]*?\*/", "", source)
    assert "https://" not in code, "a cross-origin import is blocked by COEP in WebKit"
    vendor = "/".join(TRANSFORMERS_VENDOR_SUBDIR.parts)
    assert f'from "../{vendor}/transformers.min.js"' in code
    assert f'new URL("../{vendor}/", import.meta.url)' in code, "ORT's wasm comes from this site too"
