"""Does the shipped (RU/KK-trained) model do anything sensible on ENGLISH scam calls?

A measurement before spending generation budget (PLAN item 5). Source:
`BothBosu/scam-dialogue` (Apache-2.0) -- 640 scam / 640 legit English call transcripts from a
generator that has never seen our corpus, prompts or lexicons.

Honest caveat, stated up front: this set is **US-register** (Social Security Administration,
IRS, US refunds). Our corpus is Kazakhstani. A low recall therefore conflates two things --
English-language transfer and US-vs-KZ institutional register -- and cannot separate them.
The FPR half is cleaner: a false alarm on a benign English call is bad wherever it happens.

Run: QORGAN_CLASSIFIER_BACKEND=linear python scripts/spikes/en_transfer/probe.py [--limit N]
"""

from __future__ import annotations

import argparse
import re
from collections import Counter

from datasets import load_dataset

from qorgan.classifier import predict
from qorgan.config import get_config
from qorgan.eval.intervals import clopper_pearson

_TURN = re.compile(r"\b(caller|receiver)\s*:\s*", re.I)


def to_utterances(dialogue: str) -> list[tuple[str, str]]:
    """Split "caller: … receiver: …" into (speaker, text); the source has no newlines."""
    parts = _TURN.split(dialogue.strip())
    turns: list[tuple[str, str]] = []
    for i in range(1, len(parts) - 1, 2):
        speaker = "caller" if parts[i].lower() == "caller" else "callee"
        text = parts[i + 1].strip()
        if text:
            turns.append((speaker, text))
    return turns


def _stratified(rows: list[dict], per_class: int) -> list[dict]:
    """Take `per_class` rows of each label, spread evenly over the scam types."""
    out: list[dict] = []
    for label in (1, 0):
        pool = [r for r in rows if r["label"] == label]
        types = sorted({r["type"] for r in pool})
        quota = max(1, per_class // len(types))
        for scam_type in types:
            out.extend([r for r in pool if r["type"] == scam_type][:quota])
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--limit", type=int, default=0,
        help="score only N rows per class, stratified across scam types (the source is "
             "ordered by type, so an unstratified head is one scenario and misleads)",
    )
    args = ap.parse_args()

    threshold = get_config().risk_threshold
    rows = list(load_dataset("BothBosu/scam-dialogue", split="train"))
    if args.limit:
        rows = _stratified(rows, args.limit)

    tp = fn = fp = tn = 0
    by_type: Counter[str] = Counter()
    type_total: Counter[str] = Counter()
    for row in rows:
        turns = to_utterances(row["dialogue"])
        if not turns:
            continue
        transcript = "\n".join(text for _, text in turns)
        risk = predict.score(transcript).risk
        alert = risk >= threshold
        if row["label"] == 1:
            tp, fn = (tp + 1, fn) if alert else (tp, fn + 1)
            type_total[row["type"]] += 1
            if alert:
                by_type[row["type"]] += 1
        else:
            fp, tn = (fp + 1, tn) if alert else (fp, tn + 1)

    recall = tp / (tp + fn) if tp + fn else 0.0
    fpr = fp / (fp + tn) if fp + tn else 0.0
    r = clopper_pearson(tp, tp + fn)
    f = clopper_pearson(fp, fp + tn)
    print(f"\nbackend={get_config().classifier_backend} threshold={threshold}  (onnx proxy embeddings)")
    print(f"english scam calls : recall {recall:.3f} [{r.low:.3f}, {r.high:.3f}]  ({tp}/{tp + fn})")
    print(f"english legit calls: FPR    {fpr:.3f} [{f.low:.3f}, {f.high:.3f}]  ({fp}/{fp + tn})")
    print("\nrecall by scam type:")
    for scam_type, total in sorted(type_total.items()):
        hit = by_type[scam_type]
        print(f"  {scam_type:<16} {hit:>3}/{total:<4} {hit / total:.3f}")


if __name__ == "__main__":
    main()
