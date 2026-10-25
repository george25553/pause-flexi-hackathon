# Demo video script: each beat = narration line + UI actions fired when the line starts.
# chapter = storyboard section from the submission guidelines (shown as an on-screen caption).
BEATS = [
  # 0:00-0:20 Set the scene
  dict(chapter=("Set the scene", "Pause · AI in Finance · Fraud / AML"), say=
       "This is Pause, from team Flexi, for the AI in Finance track, in the fraud problem space. "
       "Pause sits inside a Georgian bank's app, between the Pay button and the money leaving. "
       "Our user is Nino. Tonight she goes out. Tomorrow, a scammer calls her pretending to be the National Bank.", do=[]),
  # 0:20-0:50 The input
  dict(chapter=("The input", "Synthetic data · plain-language commitment"), say=
       "All data here is synthetic. Nino writes a rule in plain words: don't let me spend more than one hundred lari until ten a.m., "
       "and if I want more, Luka has to approve.", do=["demo.step()"]),
  dict(say="An on-device text model picks the categories, the parser extracts the amount and the time window, and safety checks run. "
           "The AI only proposes the rule. Nino confirms it, and a fixed policy engine enforces it.", do=["sleep:5500", "demo.step()"]),
  # 0:50-1:50 System at work
  dict(chapter=("System at work", "Uncut capture · decisions made on the phone"), say=
       "Eleven p.m., a bar, thirty-eight lari. Approved.", do=["demo.step()"]),
  dict(say="Half past midnight, forty-six more. Still approved: eighty-four of one hundred used.", do=["demo.step()"]),
  dict(say="At one forty-seven, a club table for one hundred and twenty. The scam risk is low, but this breaks Nino's own rule, so Pause holds it.",
       do=["demo.step()"]),
  dict(say="She asks Luka. Luka sees only the amount, the place and the rule. He declines.", do=["demo.step()"]),
  dict(say="Two twenty a.m., a taxi home goes straight through. Transport, pharmacy and groceries are never blocked by a commitment.",
       do=["demo.step()"]),
  # 1:50-2:30 Track-specific evidence
  dict(chapter=("AI evidence", "Explanation · human approval · fallback · audit trail"), say=
       "Next day, a marketplace seller asks for a four hundred and fifty lari prepayment. Risk zero point five three, with the reasons shown. Nino cancels.",
       do=["demo.step()", "sleep:4200", "demo.step()"]),
  dict(say="Then a caller claiming to be the National Bank tells her to move three thousand lari to a safe account. "
           "The model scores zero point nine nine. Each bar is one signal's contribution: the amount, a six-day-old recipient account, "
           "the Georgian safe-account wording, and the active call.", do=["demo.step()"]),
  dict(say="Above zero point eight five, Pause never decides alone. The money stays, and the bank's fraud desk gets a case note built from the evidence. "
           "The analyst decides.", do=["demo.step()"]),
  dict(say="If the risk model fails, Pause never silently approves. Here the model is switched off, and a conservative rules-only fallback holds the transfer for thirty minutes.",
       do=["demo.tab('try')", "sleep:700", "click:#tFail", "sleep:900", "click:#tryForm button[type=submit]"]),
  dict(say="Every rule, decision and human action goes into a hash-chained audit log. Change one old record, and verification breaks.",
       do=["demo.tab('audit')", "sleep:600", "click:#verifyBtn", "sleep:2600", "click:#tamperBtn"]),
  # 2:30-3:00 Output & impact
  dict(chapter=("Output & impact", "Measured on held-out synthetic data"), say=
       "The result: a held payment instead of a lost one. At the human-review threshold, precision is ninety-six percent, "
       "and only one point two percent of normal payments see any friction. Our fairness check flags that customers over sixty see more of it, "
       "so it goes to model-risk review instead of being hidden.", do=["demo.tab('model')"]),
  dict(say="Pause. A few seconds of friction, before the money is gone.", do=[]),
]
