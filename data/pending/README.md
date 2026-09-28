# data/pending — generated, not yet folded into the corpus

Material that exists but is **deliberately not in `data/augment/`**, because `build_corpus`
globs that directory: dropping files there changes the next build and would leave the
committed `data/processed/manifest.json` and the trained weights stale.

## `register_diversity_en_negatives.jsonl` (24 rows, 12 with reassurance)

English hard negatives in the pushy-sales / insurance register, generated 2026-09-28 by
`python scripts/augment_register_diversity.py --languages en --tag en --per-tactic 0 --negatives 24`.

**Why they exist.** ADR D54 measured English against an independent generator and found
FPR 0.227, with **all 145 false positives being legitimate sales calls** (insurance 66,
telemarketing 79) — a register absent from our 50 English negatives, which also carry no
reassurance language at all. These rows are the scoped fix.

**To use them:** move into `data/augment/`, then rebuild, retrain on the device bridge and
re-run the gates *and* the independent probe:

```bash
mv data/pending/register_diversity_en_negatives.jsonl data/augment/
python -m qorgan.data.build_corpus
npm run device:serve &                       # heads train on the browser's own embeddings
QORGAN_EMBED_BACKEND=device python -m qorgan.classifier.linear_train
QORGAN_EMBED_BACKEND=device QORGAN_CLASSIFIER_BACKEND=linear \
  python -m qorgan.eval.run --split test --split authored_heldout --split ood --split shift --by-language
QORGAN_CLASSIFIER_BACKEND=linear python scripts/spikes/en_transfer/probe.py   # was 0.739 / 0.227
```
