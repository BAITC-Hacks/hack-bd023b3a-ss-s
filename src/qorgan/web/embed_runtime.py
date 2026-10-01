"""Self-host the browser embedder's runtime: transformers.js and its onnxruntime-web WASM.

`live.html` is cross-origin isolated (COOP/COEP `require-corp`) so the WASM runtimes can use
threads. WebKit -- Safari and every iPhone browser -- refuses a module worker's cross-origin
import under that policy, so `embed-worker.js` loads these files from this site's own
`/vendor/` path, never from a CDN (ADR D61). The bytes are the 3.8.1 release the golden parity
fixtures are pinned to (ADR D32: the version moves only together with the server's
onnxruntime), each verified against its sha256 before it is written.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from urllib.request import urlopen

Downloader = Callable[[str], bytes]

TRANSFORMERS_VERSION = "3.8.1"
TRANSFORMERS_BASE_URL = f"https://cdn.jsdelivr.net/npm/@huggingface/transformers@{TRANSFORMERS_VERSION}/dist"
TRANSFORMERS_FILES = {
    "transformers.min.js": "aa5002b70e789798da263f5f99c62bd3e8fcd0c119258a493c40c180648365fa",
    "ort-wasm-simd-threaded.jsep.mjs": "08fb86ec433c78bfb032c5d84a68b8e8e5a8d81268fa39e24314179a5767a5b9",
    "ort-wasm-simd-threaded.jsep.wasm": "c46655e8a94afc45338d4cb2b840475f88e5012d524509916e505079c00bfa39",
}
# Versioned, so an upgrade never mixes with a browser's cached copy of the old files.
TRANSFORMERS_VENDOR_SUBDIR = Path("vendor") / "transformers" / TRANSFORMERS_VERSION
_DOWNLOAD_TIMEOUT_SECONDS = 120


def ensure_embed_runtime(site_dir: Path, *, downloader: Downloader | None = None) -> Path:
    """`site/vendor/transformers/<version>/` holding the pinned files. A file already present
    with the right hash is kept; a download with any other hash is refused (RuntimeError)."""
    target_dir = site_dir / TRANSFORMERS_VENDOR_SUBDIR
    for name, expected in TRANSFORMERS_FILES.items():
        target = target_dir / name
        if target.exists() and _sha256(target.read_bytes()) == expected:
            continue
        payload = (downloader or _download)(f"{TRANSFORMERS_BASE_URL}/{name}")
        actual = _sha256(payload)
        if actual != expected:
            raise RuntimeError(
                f"{name} from {TRANSFORMERS_BASE_URL} has sha256 {actual}, expected {expected}; refusing to install"
            )
        target_dir.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    return target_dir


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _download(url: str) -> bytes:  # pragma: no cover - network
    with urlopen(url, timeout=_DOWNLOAD_TIMEOUT_SECONDS) as response:  # noqa: S310 - pinned https URL
        return response.read()
