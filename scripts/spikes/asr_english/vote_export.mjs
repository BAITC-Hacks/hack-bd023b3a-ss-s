// Apply the shipped vote (site/core/asr.js voteFinal) with an English handicap to captured rows and
// write what the browser would commit per utterance -- the input of meter_replay.py.
//   node scripts/spikes/asr_english/vote_export.mjs <handicap> <out.jsonl> <capture.jsonl>...
import { readFileSync, writeFileSync } from "node:fs";
import { voteFinal } from "../../../site/core/asr.js";

const [handicap, out, ...captures] = process.argv.slice(2);
const rows = captures.flatMap((path) => readFileSync(path, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l)));
const lines = rows.map((r) => {
  const voted = voteFinal({ kk: r.kk, ru: r.ru, en: r.en }, null, { en: Number(handicap) });
  return JSON.stringify({ ...r, voted });
});
writeFileSync(out, lines.join("\n") + "\n");
console.log(`${lines.length} rows voted at handicap ${handicap} -> ${out}`);
