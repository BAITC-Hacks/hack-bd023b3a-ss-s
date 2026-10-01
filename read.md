# Qorğan in plain words

*A project description for the presentation. Each part has two layers:*
**Simply** *is the version you could tell a five-year-old;*
**Under the hood** *is the technical insertion for the jury.*

---

## The 30-second version

> Bad people phone grandma, pretend to be her bank, scare her, and ask for the secret code
> from her SMS. **Qorğan** — Kazakh for *fortress* — is a little guard that listens to the
> call with her, on her own device, and lights up a warning when the caller uses a trick. It
> shows *which* words were the trick and tells her what to do. It never decides for her,
> and the call never leaves her device unless she chooses to send a report.

**Under the hood:** on-device decision support for phone-scam (social-engineering) calls in
Kazakh, Russian, code-switched and English speech. Speech recognition, the language model and the
classifier all run in the browser. The server never receives audio and only sees what the
citizen explicitly sends.

---

## 1. The problem

**Simply:** Some bad people call grandma and say *"I'm from your bank. Your money is in
danger! Hurry! Don't tell anyone! Read me the code from the SMS."* She wants to be safe, so
she does what they say, and her money is gone. The tricks are always the same: pretend to
be someone important, scare, rush, keep it secret, ask for the code.

**Under the hood:** scam calls are scripts, and scripts have recognisable tactics. Qorğan
tags **15 tactics**:

| Group | Tactics |
|---|---|
| Who they pretend to be | bank · police / government · telecom / delivery |
| Pressure | urgency · fear / threat · secrecy |
| What they ask for | SMS code (OTP) · credentials · move money to a "safe account" · pay somewhere else · install remote access |
| Lures | prize / lottery · investment · money-mule recruitment · "verification" ploy |

Job, romance and tech-support scams do not have their own tags yet.

---

## 2. What Qorğan does

**Simply:** You put the call on speaker. Qorğan listens along and fills up a **suspicion
meter from 0 to 100**. Normal calls stay low. When the caller starts using tricks, the meter
climbs and Qorğan says, in your language, *"He asked for your SMS code. A real bank never
does that. Hang up and call the number on your card."*

**Under the hood:** the pipeline runs inside the browser:

```
speakerphone audio → speech-to-text (on device) → rolling window of the conversation
  → text embedding + 6 hand-made signals → calibrated risk → 0–100 meter → evidence + advice
```

- **Speech-to-text:** Vosklet (Vosk/Kaldi compiled to WebAssembly). A Kazakh and a Russian
  recogniser run side by side and vote on every utterance. It runs faster than real time
  (real-time factor 0.06–0.08 on a desktop).
- **Understanding:** `multilingual-e5-base`, quantised to int8 ONNX (278 MB), runs in a web
  worker.
- **Six interpretable signals:**
  - five "hard" requests: secrecy, SMS code, credentials, safe account, remote access;
  - one *reassurance* signal: "we will never ask for your code". Real banks say this;
    scammers don't.
- **Decision:** a calibrated logistic regression (774 inputs) plus 15 per-tactic heads.
- **The meter:**
  - It alerts at risk ≥ 0.59, with hysteresis (in at 0.59, out at 0.49) so it doesn't
    flicker.
  - It waits for the 3rd utterance before latching, unless a hard signal fires.
  - One confident hard signal lifts the meter to at least 61 (High); two lift it to at
    least 81 (Critical).
- **One model everywhere:** the server scores with the same committed weights file the
  browser downloads, so a verdict is the same wherever it is computed.

---

## 3. It shows its work

**Simply:** Like a good student, Qorğan doesn't just say "trick!". It points at the exact
words: *"here, where he said 'tell me the code from the SMS'"*. So you can check it yourself.

**Under the hood:**
- **Grounded explanations.**
  - Every piece of evidence is a *verbatim* span of the transcript; the data schema refuses
    anything else.
  - Reasons and advice come from reviewed Kazakh and Russian templates, never from
    free-form AI text.
- **It tolerates recognition mistakes.** Speech recognition makes errors, so cue matching
  allows a bounded number of character edits over de-spaced text.
  - Measured on 272 real recogniser outputs: cue recovery went from **67 % to 76 %**.
  - False fires stayed at **0 / 160**.

---

## 4. You decide, always

**Simply:** Qorğan is a friend who whispers *"careful!"*, not a boss. It never hangs up for
you, never blocks anyone and never tells on anybody unless you ask it to.

**Under the hood:** human-in-the-loop by design: nothing auto-blocks, auto-reports or hangs
up. The page says plainly that an AI produces the verdict and that it can be wrong, as
Kazakhstan's Law "On Artificial Intelligence" (No. 230-VIII) expects. Qorğan analyses the
**caller's words as text**. It does no voice, emotion or identity analysis, and speaker
biometrics are deliberately out of scope.

---

## 5. Your call stays home

**Simply:** Your call is like a diary with a lock: it stays on your device. Only if you
press **"Send report"** does a cleaned copy go out, and you can read and edit it first. Phone
numbers are turned into secret codes, so nobody can read them. You get a receipt, and with
it you can delete your report whenever you want.

**Under the hood:** privacy is enforced by automated architecture tests, not just by promises.
- No server route accepts audio.
- The stateless analysis endpoint stores nothing.
- **Exactly two routes can create a report:** the citizen's, and a consented partner's. Every
  route that writes anything is listed in the tests, so a new one cannot slip in unnoticed.
- **Phone numbers:**
  - Numbers are stored only as an **HMAC-SHA256 digest** plus a coarse prefix (`+7 700 ***`).
  - Transcripts are scrubbed of phone, card and IIN numbers and e-mails before storage.
- **Every report:**
  - has a receipt and can be deleted everywhere it reached;
  - expires after **180 days on the server's clock**, removed by an automatic purge;
  - stores which version of the consent text the citizen agreed to.
- **The optional cloud second opinion** (Gemini) sends text abroad, so it is **off by
  default**. When it is switched on, each request needs the person's explicit consent.

---

## 6. Helping the grown-ups catch the gang (Level 2)

**Simply:** When many people send reports, the helpers can see that the same gang keeps
using the same phone numbers. It's like connecting the dots until you can see the whole
picture of the gang. A person always checks before anything happens.

**Under the hood:**
- **Linking reports.** Consented reports are linked into scam "organisations" through a
  **phone-number co-occurrence graph**.
  - Text similarity alone could not separate scam families (centroid cosine 0.97–0.999), so
    shared numbers are the primary link.
  - Purity and ARI are 1.00 on the synthetic seed data.
- **The analyst console:** a priority queue, flags for new schemes, and confirm / dismiss /
  merge controls.
- **Access control:**
  - Each analyst has a personal key.
  - There are **two roles**: an *analyst* sees summaries and short excerpts; only an
    *investigator* can open a full transcript.
  - Opening a full transcript requires a stated reason, and is capped at 30 opens per hour.
- **Tamper-evident audit log.** It is an HMAC hash chain, so editing, deleting or reordering
  a line is detected.
- **Partner API:** consented reports from partners such as banks, mobile operators, the
  National Bank's Anti-Fraud Center, or **inDrive** (fake-operator and payment-redirect scams
  look just like ride-hailing fraud). It enforces quotas and audits every call. What comes
  back out is aggregates only.

---

## 7. It speaks Kazakh, Russian and English

**Simply:** Grandma can speak Kazakh, Russian, or mix both in one sentence, and her grandson
might get the same trick in English. Qorğan understands all of them, and its buttons and advice
talk to each person in their language.

**Under the hood:**
- The training data covers Russian, Kazakh and mixed calls in roughly equal parts, plus English
  calls set in Kazakhstan (Kaspi, Halyk, eGov, tenge) — "Kazakhstan in English", not a US corpus.
- English is the newest and weakest language: against an independent English dataset it catches
  0.739 of scams but raises false alarms on 0.227 of legitimate calls (mostly pushy sales calls),
  so it is not yet at Russian/Kazakh quality.
- Two speech recognisers run with a per-utterance vote.
- The interface, the advice and the explanations come in **қазақша / русский / English**.
  Switching language mid-call re-renders the advice already on screen without restarting the call.

---

## 8. How we taught it

**Simply:** We wrote lots of pretend phone calls: tricky ones, and normal ones that *look*
tricky, like a real bank calling about a real card. Qorğan practised on them like flashcards.
Then we tested it on calls it had never seen.

**Under the hood:**
- **2,200 synthetic dialogues** (Russian, Kazakh, mixed and English).
  - Generated with Gemini (self-instruct), then **re-labelled independently** by a second pass
    that never saw the prompt.
  - Scrubbed of personal data, deduplicated, and split deterministically.
- **Training set:** 1,880 calls, 896 scams and 984 legitimate calls, and every one of those
  legitimate calls is a hard negative.
  - It includes speech-recognition-styled copies (lowercase, no punctuation, numbers as words),
    so the model learns what recognised speech looks like.
- **Separate test sets:** hand-written calls, disfluent out-of-distribution calls, adversarial
  rewrites without the cue words, and **`shift`**: 66 calls written by a *different* generator.
- **Training:** the classifier retrains in seconds on a CPU; no GPU is needed anywhere. It is
  trained on the exact embeddings the browser produces, so server and device agree.

---

## 9. The honest report card

**Simply:** On tests written in the same style as the practice calls, Qorğan catches almost
every trick and never scares anyone for nothing. On a test written by a *different* teacher,
it catches a bit under **half** of the tricks. We say that out loud, because pretending would be worse.

**Under the hood:** threshold 0.59, device embeddings, 95 % Clopper–Pearson intervals.

| Test set | What it is | False alarms (FPR) | Scams caught (recall) |
|---|---|---|---|
| test | same generator as training (ru, kk, mixed, en; n=143) | **0.000** [0.000, 0.060] | 1.000 |
| authored_heldout | hand-written calls | **0.000** [0.000, 0.142] | 0.889 |
| ood | disfluent, out-of-distribution | **0.000** [0.000, 0.049] | 0.932 |
| **shift** | **a different generator** | 0.030 [0.001, 0.158] | **0.455** [0.281, 0.636] |

- **The cloud second opinion** (Gemini 2.5 Pro, only on the citizen's request) catches
  **33 / 33** on `shift` with **0 / 33** false alarms. This is the trade-off: *privacy tier on
  the device, accuracy tier on request.*
- **Live meter:** on the test calls it raises the alarm on 0.988 of scams and falsely on 0.050 of
  legitimate calls; the alarm usually comes by the 3rd utterance.
- **Speed:**
  - about 7 ms per transcript on a laptop CPU;
  - in the browser, about 3 s to load the model and about 0.6 s for the first check.
- **Engineering quality:** 1,250 Python tests and 60 JavaScript tests, plus real-browser
  end-to-end checks.

---

## 10. Why false alarms matter most

**Simply:** If Qorğan cries *"wolf!"* every time the real bank calls, people stop listening,
and then it can't protect anyone. So rule number one: **don't scare people for nothing.**

**Under the hood:**
- **FPR is the primary metric.** It is always reported first, per split and per language,
  with confidence intervals.
- **Hard negatives are first-class training data:** real banks, operators, couriers and
  government services calling for real reasons.
- The **reassurance signal** ("we'll never ask for your code") pulls real bank calls down.
- **The threshold stays at 0.59.**
  - Raising it to 0.65 would have removed one false alarm but lost three real scams.
  - It would also have stopped a single SMS-code request from triggering the alert.
- **We never tune on held-out data.** Every held-out call anyone has read while debugging is
  logged, and those calls are reported separately.

---

## 11. What's next

**Simply:** Practise with real calls, work on phones too, learn more kinds of tricks, and get
grown-up experts (lawyers, native speakers, banks) to check our work.

**Under the hood:**

| Next step | Why |
|---|---|
| A locked real-call test set (60 legitimate / 40 scam, "scored, never read") | The only way to know real-world accuracy. The intake pipeline is ready; it needs partner data and legal sign-off |
| Close the cross-generator gap (recall 0.455) | Real calls, a third data generator, or distilling the cloud tier's judgement |
| Teach it real banks' own warnings | A bank saying "never tell anyone the SMS code" can still trip the meter — the training data has almost no such calls |
| English sales-call negatives | English false alarms (0.227 on an independent set) are pushy but legitimate sales calls |
| Android client | Phones can't use microphone mode yet. The benchmark target: a 3 GB-RAM phone running both recognisers at ≤ 2× real time |
| Redact numbers spoken as words | The recogniser writes "восемь семьсот…", which the scrubber doesn't catch yet |
| Job, romance and tech-support tactics | Common scams without their own tags |
| Hosting in Kazakhstan with TLS and a real database | Personal-data localisation (Law 94-V), production operations |
| Native Kazakh review, a legal owner, a licence | Trust, compliance, open-source clarity |

---

## Numbers at a glance

| | |
|---|---|
| Languages | Kazakh, Russian, code-switched, English (newest, weakest) |
| Tactics detected | 15 |
| Training / evaluation data | 2,200 synthetic dialogues (+ adversarial and cross-generator sets) |
| On-device model | multilingual-e5-base, int8 ONNX, 278 MB (+ ~106 MB speech models) |
| Alert threshold | risk ≥ 0.59 (hysteresis 0.59 / 0.49) |
| False alarms on test sets | 0.000 (test, hand-written, out-of-distribution) |
| Honest cross-generator recall | 0.455 on device · 33 / 33 with the cloud second opinion |
| Median time to alert | 3 utterances |
| Report retention | 180 days, server clock, automatic purge |
| Who decides | always a person |
