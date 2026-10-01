"""Replay captured calls through the live meter: reference text vs. what the voice mode commits.

Input: rows from vote_export.mjs (one per utterance, with the voted {language, text, confidence}).
For each dialogue it runs `qorgan.live.session.advance` twice -- the reference utterances at full
confidence, and the voted ASR utterances at their confidence -- and reports, per language, how
often the meter latches (alert) on scams and falsely latches on legitimate calls.

    QORGAN_CLASSIFIER_BACKEND=linear QORGAN_LINEAR_WEIGHTS=web \\
      python scripts/spikes/asr_english/meter_replay.py voted.jsonl
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))

from qorgan.asr.stream import CommittedUtterance  # noqa: E402
from qorgan.live.session import advance, initial_session  # noqa: E402


def _latched(utterances: list[tuple[str, float]]) -> tuple[bool, float]:
    state = initial_session("ru")
    peak = 0.0
    for text, confidence in utterances:
        if not text:
            continue
        state, update = advance(state, CommittedUtterance(text=text, confidence=max(0.0, min(1.0, confidence))))
        peak = max(peak, update.meter.score)
    return state.meter.latched, peak


def main() -> None:
    dialogues: dict[str, list[dict]] = defaultdict(list)
    for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            dialogues[row["dialogue_id"]].append(row)
    tally: dict[tuple[str, bool], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for rows in dialogues.values():
        rows.sort(key=lambda r: r["index"])
        key = (rows[0]["language"], rows[0]["is_hard_negative"])
        reference, _ = _latched([(r["reference"], 1.0) for r in rows])
        heard, _ = _latched([(r["voted"]["text"], r["voted"]["confidence"]) for r in rows if r.get("voted")])
        t = tally[key]
        t["n"] += 1
        t["ref_latched"] += reference
        t["asr_latched"] += heard
    print("language  kind        n  latched(reference)  latched(voice mode)")
    for (language, negative), t in sorted(tally.items()):
        kind = "legit" if negative else "scam"
        print(f"{language:8}  {kind:6}  {t['n']:5}  {t['ref_latched']:>18}  {t['asr_latched']:>19}")


if __name__ == "__main__":
    main()
