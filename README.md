# Pause — AI payment guardian

**Team Flexi · Fintech Hackathon (GITA × NBG), Tbilisi, October 2026**
**Track:** Direction 1, AI in the financial sector · **Problem space:** Fraud / AML

Pause sits between the Pay button and the money leaving, inside a bank's own app (or a licensed TPP's app via open-banking payment initiation). It does two things:

1. **Commitments in plain words.** A customer writes, in English or Georgian, something like *"Going out tonight. Don't let me spend more than 100 GEL until 10am. If I want more, Luka has to approve."* An on-device text model and parser turn it into a structured rule, the customer confirms it, and a deterministic policy engine enforces it. Essentials (transport, pharmacy, groceries, utilities) are never blocked.
2. **Scam risk on every payment.** A logistic-regression risk model scores 11 signals (amount vs. the customer's usual, new payee, young recipient account, scam-script language in the reference, an active phone call, new device, velocity, etc.) and returns a probability plus the contribution of each signal. A graduated friction ladder follows: allow → nudge → 30-minute cool-off → **hold for a human bank analyst** (≥ 0.85). Pause never releases or rejects a held payment on its own.

Every rule, score, decision and human action is written to an append-only, SHA-256 hash-chained audit log.

All data in this repository is **synthetic**. All people, merchants and accounts are fictional.

## Run it

The prototype is a single self-contained web page. No server, no network calls, no API keys.

```bash
# open the built page directly
open dist/local.html            # macOS  (or double-click it, or: xdg-open dist/local.html)
```

Click **Run next demo step** to walk through the 12-step scenario, or write your own commitment on the phone and send your own payments from the **Try it** tab.

### Rebuild from source

Requirements: Python 3.11+ with `numpy`, `scikit-learn`; Node.js 18+ (only for the tests).

```bash
pip install numpy scikit-learn
python3 ml/train.py        # trains the 3 models on synthetic data -> app/models.json, ml/model_card.json, ml/fixtures.json
python3 build/build.py     # inlines models, engine, demo data and fonts -> dist/index.html, dist/local.html
node tests/verify.js       # JS/sklearn parity, scenario outcomes, guardrail checks
```

`build/build.py` expects the font files from the `@fontsource` npm packages (Bricolage Grotesque, IBM Plex Sans, IBM Plex Mono, Noto Sans Georgian) under `build/fonts/`:

```bash
cd build/fonts && for p in bricolage-grotesque ibm-plex-sans ibm-plex-mono noto-sans-georgian; do npm pack @fontsource/$p; done && for t in *.tgz; do mkdir -p "${t%.tgz}" && tar -xzf "$t" -C "${t%.tgz}"; done
```

## Architecture

```
 commitment text ──► commitment category classifier (char n-gram TF-IDF + LR, EN/KA)
                     + slot parser (amount, time window, trusted contact, strictness)
                     + safety validation ──► customer confirms ──► active rule

 payment + context ──► features (11) ──► risk model (logistic regression) ──► p(scam) + per-signal contributions
                                 ▲
                 scam-language classifier on the reference text (char n-gram TF-IDF + LR, EN/KA)

 p(scam), active rules ──► POLICY ENGINE (deterministic)
        ≥ 0.85  → BANK_REVIEW: money held, case + evidence note to fraud desk, analyst decides
        rule breached → COMMITMENT_HOLD: trusted contact approves once, or wait, or cancel
        ≥ 0.60  → COOL_OFF (30 min)      ≥ 0.30 → NUDGE (reasons shown)      else ALLOW
        model error → rules-only FALLBACK (never auto-allows a large payment to a new payee)

 every step ──► append-only audit log, each entry = SHA-256(prev hash + entry)
```

| Path | What it is |
|---|---|
| `ml/train.py` | Synthetic data generator, training of all three models, metrics, fairness audit, export to JSON |
| `ml/model_card.json` | Metrics, thresholds, fairness by age band, excluded inputs, limitations |
| `app/engine.js` | On-device engine: TF-IDF/LR inference (sklearn-compatible), commitment compiler, risk scoring, policy engine, case notes, hash-chained audit log |
| `app/scenarios.js` | Synthetic customer profile and demo scenarios |
| `app/src.html` | Prototype UI (customer phone, live reasoning, fraud desk, audit log, model card, try-it form) |
| `build/build.py` | Bundles everything into one self-contained page in `dist/` |
| `tests/verify.js` | Parity and guardrail tests |
| `video/` | Narration script, TTS, screen-capture and muxing scripts used to make the demo video |

## Guardrails and controls in the code

| Risk | Control | Where |
|---|---|---|
| AI misreads a commitment | AI only proposes; rule is shown as structured fields; nothing is active until the customer confirms | `parseCommitment`, `activateCommitment` in `app/engine.js` |
| Unsafe or abusive commitments | Max 31 days; hard locks max 72 h; negative or unrealistic amounts rejected; essentials always exempt | `validatePolicy`, `ESSENTIALS` |
| Model unavailable or throws | Conservative rules-only fallback; a large payment to a new payee never auto-allows | `decide()` try/catch |
| Automated decisions on high-risk payments | ≥ 0.85 → held for a human analyst; the engine cannot release or reject a case | `openCase`, `resolve('ANALYST_DECISION')` |
| Explainability | Each decision returns every feature's contribution (coef × value); case note built only from that evidence | `score()`, `openCase()` |
| Fairness | No age, gender, ethnicity, address, nationality or income inputs; friction rate compared across age bands with a 1.5× review limit (current model: 1.86×, flagged) | `ml/train.py`, Model card tab |
| Privacy | All inference runs in the browser / on the phone; trusted contact sees only amount, place and the rule | `app/engine.js` has no network code |
| Tampering with records | Append-only hash chain; `verifyChain()` detects any edited entry | `log()`, `verifyChain()` |
| JS port drifting from trained model | Parity tests against scikit-learn outputs | `tests/verify.js` |

## Results (held-out synthetic test set, 10,000 payments, 5% scam rate)

| Metric | Value |
|---|---|
| ROC AUC | 0.974 |
| PR AUC | 0.835 |
| Precision / recall at human review (≥ 0.85) | 0.961 / 0.49 |
| Recall with any friction (≥ 0.30) | 0.77 |
| Normal payments that see any friction | 1.2% |
| Normal payments that reach a human hold | 0.11% |
| Friction ratio across age bands | 1.86× (60+ vs 18–25), above the 1.5× limit → flagged for model-risk review |

**Limitations.** Synthetic typologies only; the training scam rate (5%) is far above real-world rates, so thresholds must be recalibrated on a bank's labelled fraud data. The scam-language model covers English and Georgian templates only. The production plan adds an on-device LLM (Tether QVAC) for free-form commitments and analyst notes; this prototype does not include it.

## Third-party components

| Component | Use | Licence |
|---|---|---|
| scikit-learn | Model training (not shipped in the page) | BSD-3-Clause |
| NumPy | Training | BSD-3-Clause |
| Bricolage Grotesque (via @fontsource) | UI display font, embedded | SIL Open Font License 1.1 |
| IBM Plex Sans, IBM Plex Mono (via @fontsource) | UI fonts, embedded | SIL Open Font License 1.1 |
| Noto Sans Georgian (via @fontsource) | Georgian text, embedded | SIL Open Font License 1.1 |
| Playwright | Recording the demo video only | Apache-2.0 |
| kokoro-onnx + Kokoro-82M voice model | Voice-over for the demo video only | MIT (code), Apache-2.0 (model) |
| FFmpeg | Video encoding only | LGPL-2.1+ / GPL |

The SHA-256 implementation, TF-IDF inference and policy engine are our own code. No other runtime dependencies.

## Licence

© 2026 Team Flexi. All rights reserved. Shared with the hackathon jury for evaluation only.
