// Pause decision engine — runs fully on-device (browser or Node). No network calls.
// Models are loaded from models.json (trained by ml/train.py on synthetic data).
// Design rule: ML scores and explains; the final money decision is made by deterministic,
// auditable rules (policy engine) with a human in the loop for the riskiest cases.

(function (root) {
  "use strict";

  // ---------------- text models (char_wb TF-IDF + logistic regression, sklearn-compatible) -------------
  function charWbNgrams(text, minN, maxN) {
    const out = [];
    const words = text.toLowerCase().replace(/\s\s+/g, " ").split(/\s+/).filter(Boolean);
    for (const word of words) {
      const w = " " + word + " ";
      const len = [...w].length; // code points (Georgian is BMP, so == UTF-16 length)
      const chars = [...w];
      for (let n = minN; n <= maxN; n++) {
        let offset = 0;
        out.push(chars.slice(offset, offset + n).join(""));
        while (offset + n < len) { offset++; out.push(chars.slice(offset, offset + n).join("")); }
        if (offset === 0) break;
      }
    }
    return out;
  }
  function textLogits(text, model) {
    const [minN, maxN] = model.ngram_range;
    const counts = new Map();
    for (const g of charWbNgrams(text, minN, maxN)) if (model.features[g]) counts.set(g, (counts.get(g) || 0) + 1);
    let norm = 0; const vals = [];
    for (const [g, c] of counts) { const v = c * model.features[g][0]; vals.push([g, v]); norm += v * v; }
    norm = Math.sqrt(norm) || 1;
    const logits = model.intercept.slice();
    for (const [g, v] of vals) { const f = model.features[g]; for (let k = 0; k < logits.length; k++) logits[k] += (v / norm) * f[k + 1]; }
    return logits;
  }
  const sigmoid = (z) => 1 / (1 + Math.exp(-z));

  // ---------------- tiny synchronous SHA-256 for the tamper-evident audit chain ----------------
  function sha256(ascii) {
    const utf8 = unescape(encodeURIComponent(ascii));
    const K = [], H = [];
    let p = 2, n = 0;
    const frac = (x) => ((x - Math.floor(x)) * 4294967296) | 0;
    while (n < 64) { let prime = true; for (let f = 2; f * f <= p; f++) if (p % f === 0) { prime = false; break; }
      if (prime) { if (n < 8) H[n] = frac(Math.pow(p, 1 / 2)); K[n] = frac(Math.pow(p, 1 / 3)); n++; } p++; }
    const bytes = []; for (let i = 0; i < utf8.length; i++) bytes.push(utf8.charCodeAt(i));
    const bitLen = bytes.length * 8; bytes.push(0x80); while (bytes.length % 64 !== 56) bytes.push(0);
    for (let i = 7; i >= 0; i--) bytes.push(i >= 4 ? 0 : (bitLen >>> (i * 8)) & 0xff);
    const rotr = (x, r) => (x >>> r) | (x << (32 - r));
    for (let c = 0; c < bytes.length; c += 64) {
      const w = new Array(64);
      for (let i = 0; i < 16; i++) w[i] = (bytes[c + 4 * i] << 24) | (bytes[c + 4 * i + 1] << 16) | (bytes[c + 4 * i + 2] << 8) | bytes[c + 4 * i + 3];
      for (let i = 16; i < 64; i++) {
        const s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >>> 3);
        const s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >>> 10);
        w[i] = (w[i - 16] + s0 + w[i - 7] + s1) | 0;
      }
      let [a, b, cc, d, e, f, g, h] = H;
      for (let i = 0; i < 64; i++) {
        const S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25), ch = (e & f) ^ (~e & g);
        const t1 = (h + S1 + ch + K[i] + w[i]) | 0;
        const S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22), mj = (a & b) ^ (a & cc) ^ (b & cc);
        const t2 = (S0 + mj) | 0;
        h = g; g = f; f = e; e = (d + t1) | 0; d = cc; cc = b; b = a; a = (t1 + t2) | 0;
      }
      H[0] = (H[0] + a) | 0; H[1] = (H[1] + b) | 0; H[2] = (H[2] + cc) | 0; H[3] = (H[3] + d) | 0;
      H[4] = (H[4] + e) | 0; H[5] = (H[5] + f) | 0; H[6] = (H[6] + g) | 0; H[7] = (H[7] + h) | 0;
    }
    return H.map((x) => (x >>> 0).toString(16).padStart(8, "0")).join("");
  }

  // ---------------- constants ----------------
  const CAT_LABEL = {
    bars_nightlife: "Bars & nightlife", gambling: "Betting & casinos", crypto: "Crypto exchanges",
    online_shopping: "Online shopping", food_delivery: "Food delivery", p2p_transfers: "Transfers to people",
    all: "All non-essential spending",
  };
  const ESSENTIALS = ["transport", "pharmacy", "utilities", "groceries"]; // never blocked by a commitment
  const ACTIONS = {
    ALLOW: { label: "Approved", tone: "ok" },
    NUDGE: { label: "Check before paying", tone: "warn" },
    COOL_OFF: { label: "30-minute cool-off", tone: "hold" },
    COMMITMENT_HOLD: { label: "Held by your commitment", tone: "hold" },
    BANK_REVIEW: { label: "Held for bank fraud review", tone: "stop" },
  };

  function createEngine(models, opts = {}) {
    const R = models.payment_risk;
    const now = opts.now || (() => new Date());
    const state = { commitments: [], audit: [], cases: [], seq: 0 };

    // ---------- 1. Plain-language commitment -> structured, validated policy ----------
    function parseCommitment(textRaw, profile) {
      const text = textRaw.toLowerCase();
      const t0 = now();
      const evidence = [];
      // --- time window ---
      let end = null, windowLabel = null;
      const untilEn = text.match(/\b(?:until|till|til|by)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?/);
      const untilKa = text.match(/(\d{1,2})(?::(\d{2}))?\s*(?:საათამდე|-მდე|მდე)/);
      const u = untilEn || untilKa;
      if (u) {
        let h = parseInt(u[1], 10); const m = u[2] ? parseInt(u[2], 10) : 0;
        if (u[3] === "pm" && h < 12) h += 12; if (u[3] === "am" && h === 12) h = 0;
        end = new Date(t0); end.setHours(h, m, 0, 0); if (end <= t0) end.setDate(end.getDate() + 1);
        windowLabel = "until " + String(h).padStart(2, "0") + ":" + String(m).padStart(2, "0"); evidence.push(u[0].trim());
      } else if (/tonight|night out|ამაღამ|ღამე/.test(text)) {
        end = new Date(t0); end.setHours(6, 0, 0, 0); if (end <= t0) end.setDate(end.getDate() + 1);
        windowLabel = "tonight (until 06:00)"; evidence.push((text.match(/tonight|night out|ამაღამ|ღამე/) || [""])[0]);
      } else if (/weekend|შაბათ-?კვირ/.test(text)) {
        end = new Date(t0); end.setDate(end.getDate() + ((7 - end.getDay()) % 7)); end.setHours(23, 59, 0, 0);
        windowLabel = "this weekend"; evidence.push("weekend");
      } else {
        const nd = text.match(/(\d+)\s*(days?|დღე)/), nh = text.match(/(\d+)\s*(hours?|საათი|საათის)/);
        if (nd) { end = new Date(+t0 + parseInt(nd[1], 10) * 864e5); windowLabel = nd[1] + " days"; evidence.push(nd[0]); }
        else if (nh) { end = new Date(+t0 + parseInt(nh[1], 10) * 36e5); windowLabel = nh[1] + " hours"; evidence.push(nh[0]); }
        else if (/this week|for a week|კვირ/.test(text)) { end = new Date(+t0 + 7 * 864e5); windowLabel = "7 days"; evidence.push("week"); }
        else if (/month|თვე/.test(text)) { end = new Date(+t0 + 30 * 864e5); windowLabel = "30 days"; evidence.push("month"); }
        else if (/today|დღეს/.test(text)) { end = new Date(t0); end.setHours(23, 59, 0, 0); windowLabel = "today"; evidence.push("today"); }
      }
      const windowFound = !!end;
      if (!end) { end = new Date(+t0 + 24 * 36e5); windowLabel = "next 24 hours (default)"; }

      // --- amount (strip time expressions first so "10am" is not read as 10 GEL) ---
      const noTime = text.replace(/\b(?:until|till|til|by)\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?/g, " ")
        .replace(/\d{1,2}(?::\d{2})?\s*(?:საათამდე|-მდე|მდე)/g, " ").replace(/\d+\s*(?:days?|hours?|დღე|საათი|საათის)/g, " ");
      const am = noTime.match(/(\d+(?:[.,]\d+)?)\s*(gel|lari|ლარ[ა-ჰ]*|₾|bucks|\$)?/);
      let cap = am ? parseFloat(am[1].replace(",", ".")) : null;
      if (am) evidence.push(am[0].trim());
      const blockWord = /\b(no|block|ban|stop me|zero|nothing on)\b|don'?t let me (bet|buy|gamble|trade)|აკრძალ|დაბლოკე|არ მომცე|ნუ მომცემ/.test(text);
      if (cap === null && blockWord) cap = 0;

      // --- categories (ML, multi-label) ---
      const cm = models.commitment_categories;
      const logits = textLogits(textRaw, cm);
      const catProbs = {}; cm.classes.forEach((c, i) => (catProbs[c] = sigmoid(logits[i])));
      const detected = Object.entries(catProbs).filter(([, p]) => p > 0.5).map(([c]) => c);
      // scope: a category is a hard scope only if the user said "on/for <category>"; otherwise it's context
      const scopedPhrase = /\b(on|for|at|in)\s+\w+|ზე\b|ში\b/.test(noTime.replace(/spend more than|more than/g, ""));
      const scope = detected.length && (scopedPhrase || cap === 0) ? detected : ["all"];

      // --- override / strictness ---
      const strict = /even if i beg|no matter what|strict|no override|მკაცრად|რაც არ უნდა/.test(text);
      const nameMatch = textRaw.match(/\b(ask|let|unless|if)\s+([A-Z][a-z]+)|([A-Z][a-z]+)\s+(has to|must|can|should)\s+approve|([ა-ჰ]+)\s+(?:დაადასტურებს|უნდა დაადასტუროს)/);
      const contact = nameMatch ? (nameMatch[2] || nameMatch[3] || nameMatch[5]) : profile.trustedContact;
      const override = strict ? "none_until_expiry" : "trusted_contact";

      const conf = (cap !== null ? 0.45 : 0) + (windowFound ? 0.3 : 0.1) + (detected.length || scope[0] === "all" ? 0.2 : 0) +
        (Math.max(...Object.values(catProbs)) > 0.8 || detected.length === 0 ? 0.05 : 0);
      const policy = {
        id: "C-" + (++state.seq).toString().padStart(3, "0"),
        type: cap === 0 ? "block" : "spending_cap",
        cap_gel: cap, scope, context_categories: detected,
        window: { start: t0.toISOString(), end: end.toISOString(), label: windowLabel },
        override: { mode: override, trusted_contact: override === "trusted_contact" ? contact : null },
        essentials_exempt: ESSENTIALS, source_text: textRaw,
      };
      const issues = validatePolicy(policy);
      return { policy, confidence: Math.min(1, +conf.toFixed(2)), catProbs, evidence, issues };
    }

    // schema + safety validation: the compiled rule must be safe before the user can activate it
    function validatePolicy(p) {
      const issues = [];
      if (p.cap_gel === null || isNaN(p.cap_gel)) issues.push("No amount found — say e.g. 'max 100 GEL'.");
      if (p.cap_gel !== null && p.cap_gel < 0) issues.push("Amount cannot be negative.");
      if (p.cap_gel !== null && p.cap_gel > 100000) issues.push("Amount looks unrealistic.");
      const hours = (new Date(p.window.end) - new Date(p.window.start)) / 36e5;
      if (hours > 24 * 31) issues.push("Commitments are limited to 31 days.");
      if (p.override.mode === "none_until_expiry" && hours > 72) issues.push("Hard locks are limited to 72 hours (safety).");
      return issues;
    }

    function activateCommitment(policy) {
      const c = { ...policy, spent: 0, active: true };
      state.commitments.push(c);
      log("COMMITMENT_ACTIVATED", { commitment: c.id, cap_gel: c.cap_gel, scope: c.scope, window: c.window, override: c.override }, "user");
      return c;
    }

    // ---------- 2. Risk model: features -> probability + per-feature contributions ----------
    function features(pay, profile, ctx) {
      const median = profile.medianPayment;
      const known = profile.knownPayees.includes(pay.payee);
      const ref = models.reference_text;
      const refScore = pay.reference ? sigmoid(textLogits(pay.reference, ref)[0]) : 0;
      const h = (pay.time || now()).getHours();
      const recent = profile.recentTimes.filter((t) => (pay.time || now()) - t < 36e5).length;
      return {
        amount_vs_usual: Math.max(-1, Math.min(2, Math.log(pay.amount / median) / Math.log(50))),
        new_payee: known ? 0 : 1,
        to_individual: pay.payeeType === "individual" ? 1 : 0,
        international: pay.country && pay.country !== "GE" ? 1 : 0,
        night_time: h < 6 ? 1 : 0,
        scam_language: refScore,
        call_in_progress: ctx.callActive ? 1 : 0,
        new_device: ctx.newDevice ? 1 : 0,
        young_payee_account: pay.payeeAccountAgeDays != null && pay.payeeAccountAgeDays < 30 ? 1 : 0,
        velocity: Math.min(recent / 5, 1),
        share_of_balance: Math.max(0, Math.min(1, pay.amount / profile.balance)),
      };
    }
    function score(fx) {
      let z = R.intercept; const contrib = [];
      R.features.forEach((f, i) => { const c = R.coef[i] * fx[f.key]; z += c; contrib.push({ key: f.key, label: f.label, value: fx[f.key], contribution: c }); });
      contrib.sort((a, b) => b.contribution - a.contribution);
      return { p: sigmoid(z), logit: z, contrib };
    }

    // ---------- 3. Policy engine: deterministic decision on top of the scores ----------
    function decide(pay, profile, ctx = {}) {
      const t = pay.time || now();
      let fx, s, fallback = false;
      try {
        if (ctx.simulateModelFailure) throw new Error("model unavailable");
        fx = features(pay, profile, ctx); s = score(fx);
      } catch (e) {
        // FALLBACK: conservative rules-only path, never silently allow a risky payment
        fallback = true;
        const big = pay.amount > 10 * profile.medianPayment, newP = !profile.knownPayees.includes(pay.payee);
        s = { p: big && newP ? 0.7 : 0.35, contrib: [], logit: null };
      }
      const T = R.thresholds;
      const essential = ESSENTIALS.includes(pay.category);
      const active = state.commitments.filter((c) => c.active && new Date(c.window.start) <= t && t <= new Date(c.window.end));
      const inScope = active.filter((c) => !essential && (c.scope.includes("all") || c.scope.includes(pay.category) ||
        (pay.payeeType === "individual" && c.scope.includes("p2p_transfers"))));
      const breached = inScope.find((c) => c.spent + pay.amount > c.cap_gel);

      let action, reasons = [], caseId = null;
      const top = s.contrib.filter((c) => c.contribution > 0.4).slice(0, 4).map((c) => c.label);
      if (s.p >= T.bank_review) {
        action = "BANK_REVIEW"; reasons = top;
        caseId = openCase(pay, profile, fx, s);
      } else if (breached) {
        action = "COMMITMENT_HOLD";
        const left = Math.max(0, breached.cap_gel - breached.spent);
        reasons = [`Your commitment ${breached.id}: max ${breached.cap_gel} GEL ${breached.window.label}`,
          `Already spent ${breached.spent.toFixed(0)} GEL · ${left.toFixed(0)} GEL left`];
        if (s.p >= T.nudge) reasons.push(...top);
      } else if (s.p >= T.cool_off) { action = "COOL_OFF"; reasons = top; }
      else if (s.p >= T.nudge) { action = "NUDGE"; reasons = top; }
      else action = "ALLOW";
      if (essential && active.length) reasons.push("Essential category — commitments never block it");
      if (fallback) reasons.unshift("Risk model unavailable — conservative rules-only fallback used");

      if (action === "ALLOW") inScope.forEach((c) => (c.spent += pay.amount));
      const decision = { action, p: s.p, reasons, features: fx || null, contrib: s.contrib, fallback, caseId,
        commitment: breached ? breached.id : null, override: breached ? breached.override : null, essential };
      log("PAYMENT_DECISION", { payee: pay.payee, amount: pay.amount, category: pay.category, action,
        risk: +s.p.toFixed(4), model: fallback ? "FALLBACK_RULES" : models.version, commitment: decision.commitment, case: caseId }, "engine");
      return decision;
    }

    // human-in-the-loop resolution of holds
    function resolve(kind, ref, outcome, actor) {
      log(kind, { ref, outcome }, actor);
      if (kind === "TRUSTED_CONTACT_DECISION" && outcome === "approved") {
        const c = state.commitments.find((x) => x.id === ref.commitment); if (c) c.spent += ref.amount;
      }
      if (kind === "ANALYST_DECISION") { const k = state.cases.find((x) => x.id === ref); if (k) k.status = outcome; }
    }

    // ---------- 4. Case for the bank's fraud team, with an evidence-based note ----------
    function openCase(pay, profile, fx, s) {
      const id = "FR-" + (2041 + state.cases.length);
      const typ = fx.call_in_progress && fx.scam_language > 0.5 ? "Bank / NBG impersonation — 'safe account' transfer"
        : fx.international && fx.scam_language > 0.5 ? "Investment / crypto scam"
        : fx.new_device && fx.night_time ? "Account takeover" : "Authorised push-payment scam (unclassified)";
      const mult = pay.amount / profile.medianPayment;
      const lines = [];
      lines.push(`${profile.name} attempted ${fmt(pay.amount)} GEL to ${fx.new_payee ? "a NEW" : "a known"} ${pay.payeeType === "individual" ? "private recipient" : "merchant"} “${pay.payee}”.`);
      if (fx.young_payee_account) lines.push(`Recipient account opened ${pay.payeeAccountAgeDays} days ago.`);
      if (fx.call_in_progress) lines.push("A phone call was active during the payment.");
      if (fx.scam_language > 0.5) lines.push(`Reference “${pay.reference}” matches known scam scripts (text score ${fx.scam_language.toFixed(2)}).`);
      lines.push(`Amount is ${mult.toFixed(0)}× the customer's median payment and ${(fx.share_of_balance * 100).toFixed(0)}% of balance.`);
      const k = { id, status: "open", typology: typ, risk: s.p, payment: pay, note: lines, contrib: s.contrib, opened: now(),
        recommended: ["Call the customer on their registered number (not the number they are talking to)",
          "Do not release until the customer confirms without a third party on the line",
          "If confirmed scam: report recipient account to the receiving bank for mule review"] };
      state.cases.push(k);
      log("CASE_OPENED", { case: id, typology: typ, risk: +s.p.toFixed(4) }, "engine");
      return id;
    }

    // ---------- 5. Append-only, hash-chained audit log ----------
    function log(event, data, actor) {
      const prev = state.audit.length ? state.audit[state.audit.length - 1].hash : "GENESIS";
      const entry = { n: state.audit.length + 1, ts: now().toISOString(), actor, event, data, prev };
      entry.hash = sha256(prev + JSON.stringify({ n: entry.n, ts: entry.ts, actor, event, data }));
      state.audit.push(entry);
      return entry;
    }
    function verifyChain() {
      let prev = "GENESIS";
      for (const e of state.audit) {
        const h = sha256(prev + JSON.stringify({ n: e.n, ts: e.ts, actor: e.actor, event: e.event, data: e.data }));
        if (h !== e.hash || e.prev !== prev) return { ok: false, brokenAt: e.n };
        prev = e.hash;
      }
      return { ok: true, entries: state.audit.length };
    }
    const fmt = (n) => Number(n).toLocaleString("en-US", { maximumFractionDigits: 0 });

    return { state, parseCommitment, activateCommitment, features, score, decide, resolve, log, verifyChain,
      refScore: (t) => sigmoid(textLogits(t, models.reference_text)[0]),
      catProbs: (t) => textLogits(t, models.commitment_categories).map(sigmoid) };
  }

  const api = { createEngine, charWbNgrams, textLogits, sigmoid, sha256, CAT_LABEL, ACTIONS, ESSENTIALS };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.Pause = api;
})(typeof window !== "undefined" ? window : globalThis);
