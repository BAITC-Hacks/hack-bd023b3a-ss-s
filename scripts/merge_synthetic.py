"""Merge a per-language generation batch into the main synthetic corpus (ADR D54).

`qorgan.data.generate` writes one file per config, and `build_corpus` reads a single
`output_path`. English is generated separately (`configs/corpus_en.yaml`) so that adding it
does not regenerate ru/kk/mixed — which would change every existing dialogue, and therefore
every number in the eval report, for no reason.

Merge is by dialogue id: ids already present are left untouched, so re-running is a no-op and
a partial batch can be topped up. Rows are validated as `Dialogue`s on the way through; a
batch we cannot parse is one we must not merge.

Run: python scripts/merge_synthetic.py data/synthetic/dialogues_en.jsonl
     python scripts/merge_synthetic.py data/synthetic/dialogues_en.jsonl --into data/synthetic/dialogues.jsonl
"""

from __future__ import annotations

import argparse
import collections
from pathlib import Path

from qorgan.data.schema import Dialogue


def read_dialogues(path: Path) -> list[Dialogue]:
    rows: list[Dialogue] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(Dialogue.model_validate_json(line))
        except Exception as exc:  # noqa: BLE001 -- re-raised with position, without content
            raise ValueError(f"{path.name} line {number} is not a valid Dialogue") from exc
    return rows


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Merge a generation batch into the corpus.")
    parser.add_argument("batch", type=Path, help="the per-language batch to merge in")
    parser.add_argument(
        "--into", type=Path, default=Path("data/synthetic/dialogues.jsonl"),
        help="the main synthetic corpus (default: data/synthetic/dialogues.jsonl)",
    )
    args = parser.parse_args(argv)

    existing = read_dialogues(args.into) if args.into.exists() else []
    known = {d.id for d in existing}
    incoming = read_dialogues(args.batch)
    added = [d for d in incoming if d.id not in known]

    merged = existing + added
    args.into.write_text("".join(d.model_dump_json() + "\n" for d in merged), encoding="utf-8")

    langs = collections.Counter(d.language for d in merged)
    print(f"{args.batch.name}: {len(incoming)} rows, {len(added)} new, {len(incoming) - len(added)} already present")
    print(f"{args.into.name}: {len(merged)} rows  {dict(sorted(langs.items()))}")


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
