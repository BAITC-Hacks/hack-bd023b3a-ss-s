"""Capture KK, RU AND EN recogniser output per utterance (ADR D62: English in the voice mode).

Adding an English recogniser to the per-utterance confidence vote has one real risk: on Kazakh
or Russian speech the English model may return a confident-looking hypothesis and win, which
would damage the two languages the voice mode exists for. This decodes the same synthesized
audio with all three models so any vote rule can be replayed offline (the dual-capture
pattern, `scripts/spikes/asr_cue_survival/capture_dual.py`).

    python scripts/spikes/asr_english/capture_tri.py --out data/asr_capture/tri_val.jsonl

Uses `val` by default -- never a held-out split (ADRs D35/D43). One row per utterance:
{dialogue_id, split, index, language, is_hard_negative, reference, kk, ru, en}. Resumable.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))

VOICES = {"ru": "Milena", "kk": "Aru", "mixed": "Milena", "en": "Samantha"}
EN_MODEL = "vosk-model-small-en-us-0.15"
MAX_WORDS = 60


def _dual():
    spec = importlib.util.spec_from_file_location("capture_dual", REPO / "scripts/spikes/asr_cue_survival/capture_dual.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _recognizers():
    from vosk import KaldiRecognizer, Model

    from qorgan.asr.vosk_stream import _load_recognizers
    from qorgan.config import get_config

    recognizers = dict(_load_recognizers())
    english = KaldiRecognizer(Model(model_name=EN_MODEL), get_config().asr_sample_rate)
    english.SetWords(True)
    recognizers["en"] = english
    return recognizers


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=REPO / "data/asr_capture/tri_val.jsonl")
    parser.add_argument("--splits", nargs="+", default=["val"])
    parser.add_argument("--languages", nargs="+", default=None, help="only dialogues in these languages")
    args = parser.parse_args()

    dual = _dual()
    done: set[str] = set()
    if args.out.exists():
        done = {json.loads(l)["dialogue_id"] for l in args.out.read_text(encoding="utf-8").splitlines() if l.strip()}
    todo = [(s, d) for s, d in dual.dialogues(args.splits)
            if d["id"] not in done and (not args.languages or d["language"] in args.languages)]
    print(f"{len(todo)} dialogues to capture; {len(done)} already done", flush=True)

    recognizers = _recognizers()
    scratch = args.out.parent / "_wav"
    scratch.mkdir(parents=True, exist_ok=True)
    wav = scratch / f"tri_{os.getpid()}.wav"  # parallel captures must not share the audio file
    with args.out.open("a", encoding="utf-8") as sink:
        for number, (split, dialogue) in enumerate(todo, 1):
            for index, utterance in enumerate(dialogue["utterances"]):
                text = utterance["text"]
                if len(text.split()) > MAX_WORDS:
                    continue
                try:
                    dual.synthesize(text, VOICES[dialogue["language"]], wav)
                    heard = dual.decode_both(wav, recognizers)
                except Exception as exc:  # noqa: BLE001 - one bad utterance must not stop the capture
                    print(f"  !! {dialogue['id']}#{index}: {type(exc).__name__}: {exc}", flush=True)
                    continue
                sink.write(json.dumps({
                    "dialogue_id": dialogue["id"], "split": split, "index": index,
                    "language": dialogue["language"], "is_hard_negative": dialogue["label"]["is_hard_negative"],
                    "reference": text, **heard,
                }, ensure_ascii=False) + "\n")
            sink.flush()
            if number % 10 == 0 or number == len(todo):
                print(f"  {number}/{len(todo)} dialogues", flush=True)
    wav.unlink(missing_ok=True)
    print(f"wrote {args.out}", flush=True)


if __name__ == "__main__":
    main()
