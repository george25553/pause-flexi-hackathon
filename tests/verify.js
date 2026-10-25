// Checks: (1) JS port matches sklearn outputs, (2) SHA-256 correct, (3) demo scenarios behave as designed,
// (4) guardrails: fallback path, essentials exemption, policy validation, audit-chain tamper detection.
// Run: node tests/verify.js
const fs = require("fs"), path = require("path"), assert = require("assert");
const P = require("../app/engine.js");
const models = JSON.parse(fs.readFileSync(path.join(__dirname, "../app/models.json"), "utf8"));
const fx = JSON.parse(fs.readFileSync(path.join(__dirname, "../ml/fixtures.json"), "utf8"));
const { profile, scenarios } = require("../app/scenarios.js");

let clock = new Date("2026-10-24T22:40:00+04:00");
const E = P.createEngine(models, { now: () => clock });
let fails = 0;
const ok = (c, m) => { if (!c) { fails++; console.log("FAIL", m); } else console.log("ok  ", m); };

for (const [s, p] of fx.reference_text) ok(Math.abs(E.refScore(s) - p) < 1e-3, `ref parity "${s}" js=${E.refScore(s).toFixed(4)} py=${p.toFixed(4)}`);
for (const [s, ps] of fx.commitment_categories) { const js = E.catProbs(s); ok(ps.every((p, i) => Math.abs(p - js[i]) < 1e-3), `cat parity "${s}"`); }
ok(P.sha256("abc") === "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", "sha256('abc')");

// Scenario 1: commitment
const parsed = E.parseCommitment(scenarios.commitmentText, profile);
console.log(JSON.stringify(parsed.policy, null, 1), parsed.confidence, parsed.issues);
ok(parsed.policy.cap_gel === 100 && parsed.policy.override.trusted_contact === "Luka" && parsed.policy.scope[0] === "all", "commitment compiled: 100 GEL, all scope, Luka");
E.activateCommitment(parsed.policy);
for (const step of scenarios.nightOut) {
  clock = new Date(step.time); const d = E.decide({ ...step.payment, time: clock }, profile, step.ctx || {});
  console.log(step.time, step.payment.payee, step.payment.amount, "->", d.action, d.p.toFixed(3), d.reasons.join(" | "));
  ok(d.action === step.expect, `night-out ${step.payment.payee} expected ${step.expect}`);
}
for (const step of scenarios.scam) {
  clock = new Date(step.time); const d = E.decide({ ...step.payment, time: clock }, profile, step.ctx || {});
  console.log(step.time, step.payment.payee, step.payment.amount, "->", d.action, d.p.toFixed(3), d.reasons.join(" | "));
  ok(d.action === step.expect, `scam ${step.payment.payee} expected ${step.expect}`);
}
// guardrails
const fb = E.decide({ ...scenarios.scam[scenarios.scam.length - 1].payment, time: clock }, profile, { simulateModelFailure: true });
ok(fb.fallback && fb.action !== "ALLOW", "model failure -> conservative fallback, never silent allow (" + fb.action + ")");
const bad = E.parseCommitment("block everything for 60 days even if i beg", profile);
ok(bad.issues.length > 0, "unsafe commitment rejected: " + bad.issues.join("; "));
ok(E.verifyChain().ok, "audit chain verifies (" + E.state.audit.length + " entries)");
E.state.audit[2].data.amount = 1;  // tamper
ok(!E.verifyChain().ok, "tampering detected at entry " + E.verifyChain().brokenAt);
console.log(fails ? `\n${fails} FAILED` : "\nALL CHECKS PASSED");
process.exit(fails ? 1 : 0);
