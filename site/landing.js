/* Qorğan landing -- one language control (kk / ru / en) drives the whole page, like the
   citizen page, and the choice is the same stored value (i18n-dom.js), so a visitor who picks
   Kazakh here opens "Check a call" in Kazakh. Initial language: the stored choice, else kk/ru
   from the browser, else Russian (pickLocale, ADR D47). Strings: site/i18n.js (`landing.*` and
   the shared nav/footer keys). The analyzer figure's machine log (main.js) is decorative and
   aria-hidden; the try widget (try.js) re-renders on the `qorgan:locale` event. */

import { DEFAULT_LOCALE, LOCALES, pickLocale } from "./i18n.js";
import { browserLanguages, localize, readStoredLocale, storeLocale } from "./i18n-dom.js";

const RADIOS = 'input[name="lp-lang"]';

const apply = (next, { persist = true } = {}) => {
  const locale = LOCALES.includes(next) ? next : DEFAULT_LOCALE;
  if (persist) storeLocale(locale);
  document.documentElement.lang = locale;
  document.querySelectorAll(RADIOS).forEach((radio) => { radio.checked = radio.value === locale; });
  localize(document, locale);
  document.dispatchEvent(new CustomEvent("qorgan:locale", { detail: { locale } }));
};

document.querySelectorAll(RADIOS).forEach((radio) =>
  radio.addEventListener("change", () => { if (radio.checked) apply(radio.value); })
);
apply(pickLocale({ stored: readStoredLocale(), languages: browserLanguages() }), { persist: false });

// Offline after the first visit (PLAN B4); not on a developer's localhost, where a stale shell
// would hide edits.
if ("serviceWorker" in navigator && !["localhost", "127.0.0.1"].includes(location.hostname)) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
