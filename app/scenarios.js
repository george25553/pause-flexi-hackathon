// SYNTHETIC demo data. All people, merchants and accounts are fictional.
(function (root) {
  const profile = {
    name: "Nino K. (synthetic)", firstName: "Nino", trustedContact: "Luka", balance: 4400, medianPayment: 18,
    knownPayees: ["Vake Corner Market", "Bar Nine", "TbilTaxi", "Saburtalo Pharmacy", "Luka M.", "Mama", "Gym Pulse",
      "Cafe Rioni", "MetroCard Top-up", "Silk Mobile"],
    recentTimes: [],
  };
  const scenarios = {
    commitmentText: "Going out tonight, probably getting drunk. Don't let me spend more than 100 GEL until 10am. If I want more, Luka has to approve.",
    nightOut: [
      { time: "2026-10-24T23:12:00+04:00", expect: "ALLOW",
        payment: { payee: "Bar Nine", payeeType: "merchant", amount: 38, category: "bars_nightlife", country: "GE", reference: "" } },
      { time: "2026-10-25T00:31:00+04:00", expect: "ALLOW",
        payment: { payee: "Cocktail Room Sololaki", payeeType: "merchant", amount: 46, category: "bars_nightlife", country: "GE", reference: "", payeeAccountAgeDays: 900 } },
      { time: "2026-10-25T01:47:00+04:00", expect: "COMMITMENT_HOLD",
        payment: { payee: "Club Vertigo", payeeType: "merchant", amount: 120, category: "bars_nightlife", country: "GE", reference: "VIP table", payeeAccountAgeDays: 1400 } },
      { time: "2026-10-25T02:20:00+04:00", expect: "ALLOW",
        payment: { payee: "TbilTaxi", payeeType: "merchant", amount: 14, category: "transport", country: "GE", reference: "ride home" } },
    ],
    scam: [
      { time: "2026-10-25T12:05:00+04:00", expect: "NUDGE",
        payment: { payee: "Saba T. (marketplace seller)", payeeType: "individual", amount: 450, category: "p2p_transfers", country: "GE",
          reference: "prepayment iphone 15", payeeAccountAgeDays: 45 } },
      { time: "2026-10-25T13:42:00+04:00", expect: "BANK_REVIEW", ctx: { callActive: true },
        payment: { payee: "Giorgi Beridze", payeeType: "individual", amount: 3000, category: "p2p_transfers", country: "GE",
          reference: "გადატანა უსაფრთხო ანგარიშზე", payeeAccountAgeDays: 6 } },
    ],
  };
  const api = { profile, scenarios };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.PauseDemo = api;
})(typeof window !== "undefined" ? window : globalThis);
