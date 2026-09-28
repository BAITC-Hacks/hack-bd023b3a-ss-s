# Qorğan — детекция телефонного мошенничества (GovTech Camp 2026)

**Qorğan распознаёт приёмы социальной инженерии в телефонных разговорах на казахском,
русском и смешанной речи, объясняет *почему* звонок выглядит мошенническим, и собирает
согласованные обращения граждан в «организации» для аналитика. Решение всегда принимает
человек — система ничего не блокирует и никого не отключает.**

Анализ Уровня 1 выполняется **на устройстве гражданина**: страница загружает
`multilingual-e5-base` (int8 ONNX) и веса модели прямо в браузер. Ни один маршрут сервера
не принимает аудио; содержимое звонка покидает устройство только по явному согласию, когда
гражданин сам отправляет обращение.

---

## 1. Задача

Телефонное мошенничество в Казахстане — массовая проблема. По цифрам, которые
Антифрод-центр Нацбанка РК озвучивал в публичных брифингах, с июля 2024 по февраль 2026
зафиксировано более 111 000 инцидентов, из них порядка 21 000 — ложные телефонные звонки
(первичного открытого датасета центр не публикует, поэтому цифру приводим как
ориентир, а не как измерение). Существующие меры работают на уровне транзакций и номеров —
то есть *после* разговора. Размеченного корпуса мошеннических разговоров в официальном
контуре нет.

Qorğan закрывает именно этот разрыв: он работает с **содержанием разговора** и даёт
гражданину объяснённое предупреждение в момент звонка, а государству — картину
организованных схем, собранную только из добровольных обращений.

**Два пользователя.** Гражданин (Уровень 1) — проверка звонка на своём устройстве.
Аналитик/правоохранитель (Уровень 2) — приоритетная очередь схем, построенная
исключительно на согласованных обращениях.

---

## 2. Что работает сегодня

Измеримое состояние на 28.09.2026. Все числа — вывод тестового харнесса, с доверительными
интервалами; основная метрика проекта — **FPR (доля ложных тревог)**, а не recall: ложная
тревога на настоящем звонке из банка разрушает доверие к продукту.

| Набор | FPR [95% ДИ] | Recall [95% ДИ] | N |
|---|---|---|---|
| `test` | 0.000 [0.000, 0.060] | 1.000 [0.957, 1.000] | 143 |
| `authored_heldout` (ручной) | 0.000 [0.000, 0.142] | 0.889 [0.653, 0.986] | 42 |
| `ood` (вне распределения) | 0.000 [0.000, 0.049] | 0.932 [0.813, 0.986] | 118 |
| `shift` (**другой генератор**) | 0.030 [0.001, 0.158] | 0.455 [0.281, 0.636] | 66 |

По языкам на `test`: kk, ru, mixed, en — везде FPR 0.000 / recall 1.000.
Потоковый режим (звонок по репликам): ложная фиксация 3/60, срабатывание 0.988,
медиана — 3 реплики до тревоги.

**Честная оговорка, которую мы держим на виду.** `shift` — это 66 звонков, написанных
*другим* генератором, который не видел ни нашего корпуса, ни промптов, ни словарей. Recall
0.455 — и это настоящая цифра качества, а не 1.000 на `test`. Все остальные наборы делят
генератор с обучающей выборкой. Настоящих записей звонков у нас пока нет (см. §6).

**Что реализовано:**

- **Уровень 1, на устройстве** — PWA: распознавание речи в браузере (два движка Vosk,
  KK + RU, голосование по репликам), скользящее окно, калиброванная шкала подозрительности
  0–100, подсвеченные дословные триггер-фразы, теги тактик, объяснение и советы на
  KK / RU / EN, итог звонка и **редактируемое обращение с явным согласием**.
- **Уровень 2, для аналитика** — очередь организаций по номерному графу, флаг новой схемы,
  детализация; доступ к полной расшифровке требует роли следователя, кода цели и
  попадает в **HMAC-цепочку аудита**.
- **Приватность, закреплённая тестами** (`tests/test_architecture.py`): аудио не принимает
  ни один маршрут; `/api/analyze` ничего не сохраняет; у хранилища аналитика ровно два
  входа; номера хранятся только как HMAC-дайджест + префикс `+7 700 ***`; расшифровки
  очищены от ПДн; у каждого обращения есть квитанция, его можно удалить, и оно истекает.
- **Правовая оценка** — `docs/LEGAL_ASSESSMENT.md`: разбор ЗРК «О персональных данных»
  (ст. 7, 9, 12, 16, 17, 19-1), Закона об ИИ № 230-VIII и Цифрового кодекса применительно
  к нашим потокам данных, со списком разрывов до пилота.
- **Качество**: 1257 тестов Python + 60 JS (включая пословную сверку браузерного и
  серверного расчёта на золотых фикстурах), 51 архитектурное решение (D1–D54) в `docs/DECISIONS.md`.

---

## 3. Команда и роли

| Участник | Зона ответственности |
|---|---|
| **Имангали** | Продукт и рынок: исследование рынка и конкурентов, позиционирование и value proposition, product narrative и ключевые сообщения. Сборка pitch deck и презентация концепта — проблема, ценность решения, почему это интересно пользователю и рынку. |
| **Сатжан** | Аудит проекта и данных, исследование рынка, законодательства и конкурентов, поиск технических проблем, подготовка к защите (Q&A, позиционирование, питч), ревью заявки на ресурсы. |
| **Санжар** | Разработка: модель и корпус, on-device пайплайн (PWA, ASR, инференс в браузере), оценка качества и харнесс, приватность как архитектура. |
| **Ақылжан** | Разработка: контроль доступа аналитика и аудит, приватность обращений, локализация интерфейса, правовая оценка, сборка и рантайм. |

---

## 4. Ход работы по неделям

Даты и содержание восстановлены по истории коммитов и журналу решений
(`docs/DECISIONS.md`), где у каждого решения стоит дата.

### Фаза 0 — отборочный этап (10–17 июля)

Спринт отбора: скелет проекта, таксономия из 15 тактик, синтетический корпус (Gemini),
первый классификатор и работающее демо «расшифровка → риск → объяснение». Уже тогда был
заложен принцип, который мы дальше не нарушали: **объяснение строится на дословных
фрагментах разговора, а не на свободном тексте модели**. 25 коммитов.

### Неделя 1 (4–10 сентября) — рынок, позиционирование, аудит

Кода в этой неделе нет намеренно: работа шла над тем, *что* именно строить.
Имангали собрал анализ рынка и конкурентов, сформулировал позиционирование и value
proposition, продумал product narrative. Сатжан провёл аудит проекта и данных, изучил
законодательство и конкурентов, собрал список технических проблем. Параллельно
готовился бриф для стейкхолдеров и запрашивались интервью с аналитиками
(`docs/PLAN_2026-09.md`, §7 и C7).

### Неделя 2 (11–17 сентября) — внешний разбор, разворот и новая архитектура

Ключевая неделя проекта. Независимый совет из трёх экспертных мандатов (Инженер,
Экономист, Red Team) вынес вердикт: **«принять с условиями, но не в текущем виде»** —
прослушивание звонков на сервере и государственный дашборд признаны преждевременными и
рискованными (`qorgan-council-verdict.md`).

Мы приняли это и развернули архитектуру:

- **Решения D12–D13**: сервер больше не принимает аудио; перехват оператором убран из
  дорожной карты навсегда; у Уровня 2 остаётся **единственный вход — согласованное
  обращение гражданина**.
- **D14, D17–D23**: минимизация хранения (хэшированные номера, очищенные расшифровки),
  выбор эмбеддера, партнёрский API с квотой и аудитом, агрегаты по умолчанию для аналитика,
  «новая схема» требует подтверждения.
- 11 сентября финализирован план `docs/PLAN_2026-09.md`; к 17 сентября закрыты стадии 1–3.

### Неделя 3 (18–24 сентября) — on-device, честные метрики, речь

- **D25–D26**: распознавание речи перенесено в браузер (Vosklet, два движка KK + RU);
  Whisper отклонён по измерениям; телефоны закрыты до прохождения бенчмарка.
- **D32–D33**: обнаружено, что WebGPU ломает int8-граф, а «остаточная погрешность рантайма»
  была расхождением версий ONNX Runtime. Модель теперь **обучается и оценивается на
  эмбеддингах самого браузера** — числа описывают то, что видит пользователь.
- **D35**: введён `shift` — 66 звонков от другого генератора. Recall упал с 0.95 до 0.242.
  Это неприятная цифра, и мы сделали её главной.
- **D39**: сопоставление триггер-фраз перестало ломаться об ошибки распознавания
  (измерено на 272 реальных выходах распознавателя); восстановление подсказок 67 % → 76 %.
- **D42–D43**: расширение регистра обучающих данных подняло `shift` 0.242 → 0.364;
  цена зафиксирована в журнале, а не спрятана.

### Неделя 4 (25–28 сентября) — доступ, право, третий язык, надёжность

- **D44–D46**: гражданин просматривает, редактирует и подтверждает обращение до отправки;
  консоль аналитика — персональные ключи, роли, коды цели и аудит в виде HMAC-цепочки.
- **D47, D52**: интерфейс и **содержание** (советы, названия тактик, объяснения) на
  KK / RU / EN — раньше английский интерфейс показывал русские тексты.
- **D49**: закрыты маршруты, которых «не должно было быть»: облачный тир выключен по
  умолчанию и требует отдельного согласия, серверная сессия звонка удалена, хранение
  считается по часам сервера.
- **D50–D51**: найден и исправлен реальный дефект — словарь подсказок писал «SMS» латиницей,
  а живое распознавание выдаёт «СМС» кириллицей, из-за чего **53 строки корпуса теряли
  жёсткий сигнал**. После исправления recall на `test` 0.984 → 1.000.
- **D53**: три ошибки надёжности клиента LLM (зависание на 83 минуты при 0 % CPU,
  необработанный обрыв соединения, потеря целой партии при записи в конце).
- **D54**: английский стал **третьим языком звонка** (170 диалогов, казахстанские реалии
  на английском). Побочный эффект, которого мы не ждали: `shift` улучшился до
  **FPR 0.030 / recall 0.455** — четвёртый язык помог качеству на казахском и русском.

---

## 5. Что известно о слабых местах

Мы держим это в документации, а не в уме:

1. **Настоящих записей звонков нет.** Все наборы — синтетика или ручные сценарии.
   Протокол приёма реальных данных готов (`docs/DATA_INTAKE.md`), правовой разбор сделан,
   но сами данные — за стейкхолдерами.
2. **Английский не на уровне казахского и русского.** На `test` — 1.000, но это тот же
   генератор, что и в обучении. На независимом генераторе: recall 0.739 при **FPR 0.227**.
   Все 145 ложных тревог — легитимные «продающие» звонки (страхование, телемаркетинг),
   которых нет в наших английских негативах. Задача понятна и оценена.
3. **Перенос между генераторами** (`shift` 0.455) — главный открытый вопрос качества.
4. **Правовые разрывы до пилота** перечислены в `docs/LEGAL_ASSESSMENT.md` §6 (M1–M11):
   основание для данных *звонящего*, хостинг в РК, уведомления, DPA с партнёром.

---

## 6. Что дальше

| Приоритет | Работа |
|---|---|
| 1 | **Реальные звонки** (A3): приём от банка/Антифрод-центра по готовому протоколу; заблокированный held-out набор. Без этого все цифры остаются синтетическими. |
| 2 | Английские негативы в «продающем» регистре — закрыть FPR 0.227. |
| 3 | Перенос между генераторами: третий генератор для обучающих данных. |
| 4 | Правовой блок M1–M11 до любого пилота (мнение адвоката по данным звонящего — на критическом пути). |
| 5 | Мобильные устройства: бенчмарк Vosklet на Android. |

---

## 7. Где что лежит

| Документ | О чём |
|---|---|
| [`docs/STATUS.md`](docs/STATUS.md) | Текущее состояние и передача дел — читать первым |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | 51 архитектурное решение (D1–D54) с датами и измерениями |
| [`docs/eval_report.md`](docs/eval_report.md) | Все числа с интервалами, источник истины |
| [`docs/LEGAL_ASSESSMENT.md`](docs/LEGAL_ASSESSMENT.md) | Правовая оценка по законодательству РК |
| [`docs/PLAN_2026-09.md`](docs/PLAN_2026-09.md) | План после вердикта совета |
| [`qorgan-council-verdict.md`](qorgan-council-verdict.md) | Вердикт независимого совета |
| [`data/README.md`](data/README.md) | Происхождение данных (ТЗ §9) |
| [`docs/DATA_INTAKE.md`](docs/DATA_INTAKE.md) | Протокол приёма реальных звонков |

---

# Technical reference (English)

## What it does — three tabs, one pipeline

| Tab | Persona | What happens |
|---|---|---|
| **Level 1 — Call check** | citizen | Paste/pick a transcript → calibrated **risk score** → **explained** alert: highlighted trigger phrases, tactic tags, plain RU/KK reason, honest confidence. |
| **Live call** | citizen | A call is analyzed **turn by turn**: streaming utterances → rolling window → **0–100 suspicion meter** (hysteresis + hard-signal floors) → grounded evidence cards → tactic-specific advice (RU/KK) → post-call summary → **consent-gated, editable report**. Input: replay a script (zero setup), or a real **microphone** (browser or local) with dual Vosk KK+RU streaming ASR. |
| **Level 2 — Analyst view** | gov analyst | KPI row, priority queue of scam **organizations** (named by dominant tactics), new-scheme flags, drill-down with tactic/activity charts — and an **Ingest** button that pulls submitted citizen reports into the analysis (a report whose number matches a known org joins it; unknown numbers become novelty candidates). |

## Quick start

```bash
# 1. Environment (Python 3.11+)
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"         # runtime + tests; ".[all]" adds the cloud tier, Streamlit harness, research paths
cp .env.example .env             # set the number-HMAC, analyst and audit-chain secrets (see the file); GEMINI_API_KEY only for the cloud tier / data-gen

# 2. Models + demo data in one go (idempotent; ~300 MB download on first run):
#    corpus splits + trained head weights from Hugging Face, the int8 ONNX embedder the
#    browser ships (self-hosted under site/models/), and the Level-2 demo seeds.
python scripts/deploy_bootstrap.py
#    ...or retrain the heads from the committed corpus (seconds, CPU):
python -m qorgan.data.build_corpus && python -m qorgan.classifier.linear_train

# 3. Run the site (landing + live call + analyst dashboard) -- analysis runs ON THE DEVICE
python -m qorgan.api             # http://localhost:8000
#    or the Streamlit dev harness (needs `pip install -e ".[harness]"`; not the product):
streamlit run app/streamlit_app.py
```

**On-device by design.** The pages under `site/` load the same `multilingual-e5-base`
int8 ONNX graph and the exported head weights (`site/models/`) and score transcripts in
the browser (`site/core/`, a 1:1 port of the Python classifier — `npm test` proves parity
on golden fixtures). The server embeds with the *same* int8 graph
(`QORGAN_EMBED_BACKEND=onnx`), so a verdict is identical wherever it is computed. No
route accepts audio; call content leaves the device only on an explicit report.

**No model, no key?** The app still runs — it degrades to a deterministic `mock` backend
so the demo scripts work out of the box.

**Harness microphone (optional):** `pip install -e ".[harness,live]"` (vosk, streamlit-webrtc,
sounddevice). First use downloads two small Vosk models (~100 MB) to `~/.cache/vosk`.
Put the call on speakerphone near the device. Without the extra, the Live tab's replay
mode still works and the mic modes show an install hint.

## The demo storyline (3 scenes)
1. **Live scam call** (`live_scam_bank_ru` scenario) — the meter climbs to Critical,
   evidence and advice appear mid-call, post-call summary offers a report.
2. **Hard negative** (`live_hard_negative_bank_ru`) — a *real* bank call does **not**
   trigger. False-positive discipline is the product's core metric.
3. **Analyst view** — submit the report from scene 1 (use a number from a seeded org,
   e.g. `+7 700 101 20 30`), then click **Ingest into analysis**: watch it land inside
   that organization.

## Evaluate

```bash
# FPR-first tables (test + authored_heldout + ASR-stress), per language
QORGAN_CLASSIFIER_BACKEND=linear python -m qorgan.eval.run \
    --split test --split authored_heldout --split ood --by-language

# Streaming eval: false-latch rate (live FPR analog), time-to-alert
QORGAN_CLASSIFIER_BACKEND=linear python -m qorgan.eval.stream \
    --split test --split authored_heldout --backend linear

# Live-meter parameter sweep on cached per-turn traces (seconds, after a ~2 min trace build)
QORGAN_CLASSIFIER_BACKEND=linear python -m qorgan.eval.meter_sweep --min-turns 1,2,3 --damping 1,2,3

# Level-2 cluster quality under number-rotation stress, with stability intervals
python -m qorgan.eval.cluster --resamples 50

# Adversarial paraphrases: cue-free (A9) and legit-sounding (A9b), paired recall vs the sources
QORGAN_CLASSIFIER_BACKEND=linear python -m qorgan.eval.adversarial
QORGAN_CLASSIFIER_BACKEND=linear python -m qorgan.eval.adversarial --split adversarial_legit

# The recogniser's register: every eval dialogue clean vs ASR-styled (lowercase, no
# punctuation, numerals as words), paired; --drop-latin is the worst case for «SMS»/«CVV»
QORGAN_CLASSIFIER_BACKEND=linear python -m qorgan.eval.asr_realism [--drop-latin]

pytest -q        # ~1,070 tests, all offline
npm test         # JS core parity with Python + the DEVICE gate (browser embeddings, seconds)
npm run gate:browser   # re-capture the browser's embeddings of the gate set (headless Chromium;
                       # `npx playwright install chromium` once) after a model/runtime change

# Retrain / evaluate on the DEVICE's embeddings (ADR D33): start the bridge, then any command
# above with QORGAN_EMBED_BACKEND=device (vectors are cached; the first pass takes minutes)
npm run device:serve -- --pages 4 &
QORGAN_EMBED_BACKEND=device python -m qorgan.classifier.linear_train
```

Shipped numbers (threshold 0.59, 2026-09-24, computed on the **browser's own embeddings** —
ADR D33, so they describe what the device decides, browser gate 0/200; corpus repaired, ADR D34;
training register widened, ADR D42):
**test FPR 0.000 / recall 0.984 · authored_heldout FPR 0.000 / recall 0.889 · ood FPR 0.000 /
recall 0.932 · ASR-styled FPR 0.000 on every split · adversarial (cue-free) recall 0.945 ·
adversarial (legit-sounding) recall 0.835**. Read them with their intervals: `authored_heldout` is
**hand-written, not real calls** (18 scam / 24 legit), so its FPR of 0.000 has a 95 %
Clopper–Pearson interval of **[0.000, 0.142]** and its recall of 0.889 is 16/18 — the two
misses are named in the report; test's 0.000 is **[0.000, 0.070]** on 51 negatives; five
authored negatives were read during feature engineering and are reported separately
(`data/anchors/inspection_ledger.yaml`). The server's native runtime is a cosine-0.98 proxy
of the device and disagrees on 6/200 borderline calls — reported, not hidden. The harness
prints intervals on every run.

**The number to lead with, though, is this one (ADRs D35/D42/D43):** on a 66-call split
written by a *second generator* (`shift`: 33 scams / 33 confusable legit, ru / kk / mixed,
authored without sight of the corpus or the lexicons — `data/README.md`), the same model has
**recall 0.364 [0.204, 0.549] and FPR 0.061 [0.007, 0.202]** — 12 of 33 scams. It was 8 of 33
until the training register was widened (D42), which is the honest measure of how much of the
earlier gap was one generator's house style rather than scam semantics. Both of that split's
false positives are rows read while debugging and are ledger-marked, so the harness also
prints `shift (clean)` — FPR **0.000 [0.000, 0.112]** on the 64 rows never looked at (D43). Every other
split above shares its generator (Gemini) with the training data, so their recall is largely
that generator's register. The reassurance feature still holds (real fraud alerts score
≤ 0.01) and the FPR story survives, but until real calls exist the recall claim is "one
generator's scams", and the `shift` table in the eval report is the honest one. The cloud
second opinion (`llm` backend, Gemini 2.5 Pro, offered on the citizen's explicit request) scores
the same 66 calls at **33 / 33 recall and 0 / 33 FPR** (ADR D38) — that is the accuracy tier;
the device model is the privacy tier. The gap between 12/33 and 33/33 is the honest measure of
what running on-device currently costs, and closing it needs real calls (A3), not more
synthetic data. Methodology + caveats: [`docs/eval_report.md`](docs/eval_report.md), data
provenance: [`data/README.md`](data/README.md).

## Microphone mode (on-device speech recognition)

On desktop browsers the live page can listen to a call directly: Kazakh and Russian Vosk
models run in the browser (Vosklet/WASM, one instance each), the better hypothesis wins per
utterance, and the transcript feeds the same on-device classifier and meter as replay —
**no audio or text leaves the device** (ADR D26). Requirements the server already meets:
`/live.html` and `/core/*` are served cross-origin isolated (COOP/COEP) because the
recogniser needs SharedArrayBuffer; `python scripts/deploy_bootstrap.py` installs the
hash-pinned Vosklet runtime under `site/vendor/` and packages the two model tarballs
(~106 MB, downloaded once by the browser) — nothing is loaded live from a CDN. Phones are disabled until the
Android bench passes (`scripts/spikes/vosklet_bench/`).

## Real calls (when they arrive)

`docs/DATA_INTAKE.md` is the policy and protocol: encrypted/on-prem delivery, a
`batch.yaml` + `calls.csv` batch format, `python scripts/ingest_partner_calls.py <batch>`
(scrub → hashed number linkage → first-come allocation into a hash-locked
`real_heldout_v2` of 60 legit / 40 scam, the rest to `real_train`). The locked set is
scored, never read, and only at release points. `data/real/` never enters git.

## Reports API (consented ingress) & privacy

`POST /api/reports` is the only way call content enters the analyst layer, and only on an
explicit user action. The server stores the transcript PII-scrubbed, the caller number as
a salted HMAC digest + prefix (`+7 700 ***`), returns exactly what it kept plus a receipt,
and `DELETE /api/reports/{receipt}` forgets it everywhere (`python -m qorgan.reports.purge`
applies the retention window). Set `QORGAN_NUMBER_HMAC_KEY` (see `.env.example`); without
it the server refuses reports that carry a number. No route accepts audio; these
invariants are enforced by `tests/test_architecture.py` (ADRs D12–D14).

## Analyst dashboard exposure

`admin.html` asks for an **analyst key** (`QORGAN_ANALYST_KEYS="id:secret:role,..."`; unset =
the console is closed) and then shows organization aggregates and excerpts; the identity in
every log line comes from the key. Reading a whole call needs the **investigator** role and a
stated purpose (`pattern_review` / `citizen_request` / `partner_request`); the server writes
`analyst · case.open · incident:<id> · purpose` to `data/processed/audit_log.jsonl` before it
answers (ADR D20). That log is a keyed hash chain (`QORGAN_AUDIT_CHAIN_KEY`):
`python -m qorgan.audit verify` names the first edited, deleted or reordered entry. Analysts
can **confirm / dismiss / merge** an organization; the verdict is stored as an append-only
event keyed by the operation's numbers, so it survives re-clustering (a dismissed operation
drops to 20 % priority; ADR D24). Per-person keys are a stand-in for SSO in a deployment.

## Partner API (`/api/v1`) — consented reports in, aggregates out

A bank fraud desk, telecom or hotline can feed confirmed cases into the analyst layer and
read back the organization-level picture — without ever sending call content it does not
have to. It is a second *consented* ingress, not a bulk feed (ADR D19):

- **Auth**: `X-API-Key` per partner; keys live in the server env
  `QORGAN_PARTNER_API_KEYS="bank_a:<secret ≥16 chars>[:daily_quota],telecom_b:<secret>"`
  (unset = the API is closed; `QORGAN_PARTNER_DAILY_QUOTA` is the default budget).
- **One report per request**, preferably **structured tactic hits**; a transcript is accepted
  only if the partner already PII-scrubbed it (the server checks and refuses otherwise,
  without echoing it). `consent_basis` (a code from the data-sharing agreement) is required.
  The caller number is hashed on receipt like a citizen report. `partner_reference` makes
  retries idempotent.
- **Limits**: 60 requests/min and a rolling 24 h quota per partner (`X-Quota-Limit` /
  `X-Quota-Remaining` on every response); a content-free audit line for every action
  (`data/processed/audit_log.jsonl`).
- **Export**: `GET /api/v1/organizations` returns aggregates only — no numbers, no digests,
  no transcripts. Partners can `DELETE` only their own receipts.

```bash
export QORGAN_PARTNER_API_KEYS="bank_a:replace-with-a-32-char-secret-00000000"
python -m qorgan.api    # OpenAPI at http://localhost:8000/docs (scheme: PartnerApiKey)

# 1. a confirmed case as structured signals (preferred shape)
curl -s -X POST http://localhost:8000/api/v1/reports \
  -H "X-API-Key: replace-with-a-32-char-secret-00000000" -H "Content-Type: application/json" \
  -d '{"consent_basis":"customer_consent","tactic_ids":["otp_request","safe_account"],
       "phone_number":"+7 700 555 66 77","partner_reference":"CASE-2026-0912"}'
# -> 201 {"receipt_id": "...", "number_prefix": "+7 700 ***", "quota": {"limit":200,"used":1,...}}
# 2. the same case again -> 200 "duplicate", nothing stored, quota untouched
# 3. the organization-level picture (aggregates only)
curl -s http://localhost:8000/api/v1/organizations?locale=ru -H "X-API-Key: replace-with-a-32-char-secret-00000000"
# 4. withdraw a report
curl -s -X DELETE http://localhost:8000/api/v1/reports/<receipt_id> -H "X-API-Key: replace-with-a-32-char-secret-00000000"
```

Signals-only reports (no transcript) are stored, receipted, deletable and counted; placing
them into organizations through the number graph alone is the next Level-2 item (PLAN C9).

## Publish model/data updates (maintainers)

After a retrain: `hf auth login` (write token) then `python scripts/hf_upload.py` — it
uploads `models/linear` **together with** `data/lexicon` (the bundle hash-validates the
lexicons) and the scrubbed dataset splits. Never widen the dataset patterns: the other
`data/processed/` files (incidents, citizen reports) and raw `data/synthetic/` must stay
off the Hub.

## Layout
`src/qorgan/` (config · taxonomy · data · classifier · explain · **live** · analytics ·
asr · eval) · `app/` (Streamlit: `streamlit_app.py`, `live_view.py`, `mic_live.py`,
`analyst_view.py`) · `data/` (taxonomy · lexicons · corpus + provenance) · `tests/` ·
`docs/` (scope, architecture, decisions, status, eval report).

## Status & limits
Web prototype. The live-mic path is real (Vosk streaming, KK/RU voting) but
speakerphone-quality ASR — especially Kazakh — is the accuracy bottleneck; the meter's
confidence weighting absorbs some of it. ~1 in 6 legit calls still latches the live meter
*transiently* mid-call (documented, measured by `eval.stream`; fix candidates in
`docs/STATUS.md`). Mobile, on-device, and carrier integration are the roadmap
([`DOCUMENTATION.md`](DOCUMENTATION.md)), not this repo.
