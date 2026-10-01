import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { REPO } from "./helpers.mjs";

// Static guarantees of the three pages (site/): what the design/QA pass fixed must stay fixed.
const read = (page) => readFileSync(join(REPO, "site", page), "utf8");
const PAGES = ["index.html", "live.html", "admin.html"];

test("the analyst console keeps its script lockdown", () => {
  const html = read("admin.html");
  const csp = html.match(/http-equiv="Content-Security-Policy" content="([^"]+)"/)?.[1] || "";
  assert.match(csp, /script-src 'self'(;|$)/, "script-src stays 'self' only");
  assert.match(csp, /object-src 'none'/);
  const inline = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>/g)];
  assert.deepEqual(inline.map((m) => m[0]), [], "no inline script on the page that holds a key");
  assert.doesNotMatch(html, /\son[a-z]+="/, "no inline event handlers");
});

test("every page declares the one deliberate theme", () => {
  for (const page of PAGES) {
    assert.match(read(page), /<meta name="color-scheme" content="only light">/, page);
  }
  assert.match(read("styles.css"), /color-scheme:only light/);
});

test("in-page and cross-page anchors point at elements that exist", () => {
  const ids = (page) => new Set([...read(page).matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]));
  for (const page of PAGES) {
    for (const [, target, hash] of read(page).matchAll(/href="([\w-]*\.html)?#([\w-]+)"/g)) {
      const where = target || page;
      assert.ok(ids(where).has(hash), `${page}: href to ${where}#${hash} has no element`);
    }
  }
});

test("the landing sends citizens to the citizen page", () => {
  const html = read("index.html");
  assert.ok((html.match(/href="live\.html" data-i18n="landing\.cta_check"/g) || []).length >= 2, "header + hero call to action");
});
