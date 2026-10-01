// Replay the shipped vote (site/core/asr.js voteFinal) over a three-recogniser capture, with an
// English handicap h: English ranks with (confidence - h). Reports, per handicap, how often
// English wrongly wins on kk/ru/mixed speech (the cost) and correctly wins on English (the gain).
//   node scripts/spikes/asr_english/vote_sweep.mjs data/asr_capture/tri_val.jsonl
import { readFileSync } from "node:fs";
import { voteFinal } from "../../../site/core/asr.js";

const rows = readFileSync(process.argv[2], "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));
const pct = (n, d) => (d ? `${((100 * n) / d).toFixed(1)}%` : "-");
const handicaps = [0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3];
const byLang = (lang) => rows.filter((r) => (lang === "cyr" ? r.language !== "en" : r.language === "en"));
console.log(`rows: ${rows.length} (kk/ru/mixed ${byLang("cyr").length}, en ${byLang("en").length})`);
console.log("handicap | EN wins on kk/ru/mixed (cost) | EN wins on English (gain) | kk/ru winner changed vs 2-model vote");
for (const h of handicaps) {
  let steal = 0, gain = 0, changed = 0;
  for (const r of rows) {
    const two = voteFinal({ kk: r.kk, ru: r.ru });
    const three = voteFinal({ kk: r.kk, ru: r.ru, en: { ...r.en, confidence: r.en.confidence - h } });
    const winner = three?.language;
    if (r.language === "en") { if (winner === "en") gain++; }
    else {
      if (winner === "en") steal++;
      if (winner !== two?.language) changed++;
    }
  }
  console.log(`${h.toFixed(2).padStart(8)} | ${pct(steal, byLang("cyr").length).padStart(28)} | ${pct(gain, byLang("en").length).padStart(25)} | ${pct(changed, byLang("cyr").length)}`);
}
