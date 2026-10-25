"""
Pause — model training pipeline (synthetic data only).

Trains three small, explainable models and exports them to JSON so they can run
on-device (in the browser / phone) with no server and no data leaving the device:

  1. reference_text  : char n-gram TF-IDF + logistic regression that scores how much a
                       payment reference / chat snippet looks like a known scam script
                       (Georgian + English).
  2. commitment_cats : char n-gram TF-IDF + one-vs-rest logistic regression that maps a
                       plain-language commitment ("going out tonight, max 100 GEL on bars")
                       to spending categories.
  3. payment_risk    : logistic regression over 11 behavioural / contextual features that
                       outputs a scam probability with per-feature contributions
                       (coef * value) used as the explanation shown to user and analyst.

Everything here is synthetic. No real customer data was used.
Run:  python3 ml/train.py   ->  writes app/models.json and ml/model_card.json
"""
import json, math, random, pathlib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split, cross_val_predict
from sklearn.metrics import roc_auc_score, precision_score, recall_score, average_precision_score

SEED = 7
random.seed(SEED); np.random.seed(SEED)
ROOT = pathlib.Path(__file__).resolve().parent.parent

# ----------------------------------------------------------------------------------
# 1. Reference-text scam classifier
# ----------------------------------------------------------------------------------
NAMES = ["Nino", "Luka", "Mariam", "Giorgi", "Ana", "Dato", "Tamar", "Levan", "Salome", "Sandro",
         "ნინო", "ლუკა", "მარიამ", "გიორგი", "ანა", "დათო", "თამარ", "ლევან", "სალომე"]
LEGIT_REFS = [
    "rent {m}", "ბინის ქირა {m}", "dinner split", "for dinner {n}", "groceries", "birthday gift for {n}",
    "დაბადების დღე {n}", "utility bill", "კომუნალური", "thanks for lunch", "ტაქსი", "taxi back home",
    "concert tickets", "gym membership", "ფიტნესი", "phone top up", "ბალანსის შევსება", "tuition fee {m}",
    "სწავლის საფასური", "for the trip", "მოგზაურობა", "coffee", "ყავა", "pizza night", "books",
    "shared flat internet", "ინტერნეტი", "wedding gift", "ქორწილი", "loan repayment {m}", "სესხის შენატანი",
    "car repair", "მანქანის შეკეთება", "pharmacy", "აფთიაქი", "parking", "debt to {n}", "ვალი {n}",
    "salary advance return", "christmas present", "football tickets", "kids school trip", "ექსკურსია",
    "netflix share", "piano lessons", "dentist", "სტომატოლოგი", "flowers for mom", "ყვავილები",
]
SCAM_REFS = [
    "transfer to safe account", "უსაფრთხო ანგარიშზე გადატანა", "safe account urgent",
    "loan cancellation national bank", "სესხის გაუქმება ეროვნული ბანკი", "nbg verification fee",
    "ეროვნული ბანკის თანამშრომელი", "account verification urgent", "ანგარიშის ვერიფიკაცია სასწრაფოდ",
    "security deposit refund", "unblock card fee", "ბარათის განბლოკვა", "prepayment iphone {m}",
    "წინასწარი გადახდა", "advance payment apartment booking", "ბინის ჯავშანი წინასწარ",
    "investment profit withdrawal fee", "საინვესტიციო მოგების გატანა", "crypto investment platform",
    "კრიპტო ინვესტიცია", "customs fee for parcel", "ამანათის განბაჟება", "prize tax lottery",
    "პრიზის გადასახადი", "operator said transfer now", "bank officer instructions", "do not tell anyone",
    "არავის უთხრა", "urgent help {n} new number", "დედა ახალი ნომერია სასწრაფოდ", "anti fraud department transfer",
    "protect your savings", "დანაზოგის დაცვა", "refund of overpaid loan", "compensation release fee",
]

def fill(t):
    return t.replace("{m}", random.choice(["october", "november", "ოქტომბერი", "ნოემბერი", "sept"])) \
            .replace("{n}", random.choice(NAMES))

def noisy(s):
    r = random.random()
    if r < 0.15: s = s.upper()
    elif r < 0.30: s = s.replace(" ", "  ")
    if random.random() < 0.2: s = s + " " + random.choice(["!!", "pls", "გთხოვ", "asap", ".", ""])
    if random.random() < 0.1 and len(s) > 6:  # typo
        i = random.randrange(len(s) - 1); s = s[:i] + s[i+1] + s[i] + s[i+2:]
    return s

def make_refs(n):
    X, y = [], []
    for _ in range(n):
        if random.random() < 0.35:
            X.append(noisy(fill(random.choice(SCAM_REFS)))); y.append(1)
        else:
            X.append(noisy(fill(random.choice(LEGIT_REFS)))); y.append(0)
    return X, y

ref_X, ref_y = make_refs(6000)
ref_vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), lowercase=True, max_features=2500)
ref_M = ref_vec.fit_transform(ref_X)
ref_clf = LogisticRegression(C=4.0, max_iter=2000)
ref_clf.fit(ref_M, ref_y)

# held-out generalisation check on unseen phrasings
HOLDOUT = [("please move money to the safe account today", 1), ("გადარიცხე უსაფრთხო ანგარიშზე", 1),
           ("national bank officer asked to verify", 1), ("fee to unblock my card", 1),
           ("rent for november", 0), ("dinner with luka", 0), ("ქირა ნოემბერი", 0), ("gift for ana", 0)]
holdout_pred = ref_clf.predict_proba(ref_vec.transform([h[0] for h in HOLDOUT]))[:, 1]
ref_holdout_acc = float(np.mean([(p > 0.5) == bool(lbl) for p, (_, lbl) in zip(holdout_pred, HOLDOUT)]))

def export_text_model(vec, clf, classes):
    vocab = vec.vocabulary_
    idf = vec.idf_
    coef = clf.coef_  # (n_classes_or_1, n_features)
    feats = {}
    for term, j in vocab.items():
        feats[term] = [round(float(idf[j]), 5)] + [round(float(c), 5) for c in coef[:, j]]
    return {"analyzer": "char_wb", "ngram_range": list(vec.ngram_range), "classes": classes,
            "intercept": [round(float(b), 5) for b in clf.intercept_], "features": feats}

# ----------------------------------------------------------------------------------
# 2. Commitment category classifier (multi-label, one-vs-rest)
# ----------------------------------------------------------------------------------
CATS = {
    "bars_nightlife": ["bars", "drinks", "going out", "party", "club", "get drunk", "getting drunk", "drunk",
                       "nightlife", "pub", "alcohol", "beer", "wine bar", "cocktails", "night out",
                       "ბარი", "ბარებში", "დალევა", "ვსვამ", "წვეულება", "კლუბი", "მთვრალი", "ალკოჰოლი",
                       "ლუდი", "ღვინის ბარი", "გავდივარ", "ქეიფი"],
    "gambling": ["betting", "bets", "casino", "slots", "gambling", "poker", "sports bets", "roulette",
                 "ტოტალიზატორი", "კაზინო", "ფსონი", "სლოტები", "აზარტული", "პოკერი", "ბეთი"],
    "crypto": ["crypto", "bitcoin", "coins", "memecoins", "exchange", "trading", "usdt", "token",
               "კრიპტო", "ბიტკოინი", "კრიპტოვალუტა", "ტრეიდინგი", "მონეტები"],
    "online_shopping": ["online shopping", "clothes", "shopping", "shoes", "marketplace", "sneakers",
                        "gadgets", "online stores", "ტანსაცმელი", "შოპინგი", "ონლაინ მაღაზია", "ფეხსაცმელი",
                        "ყიდვა ონლაინ"],
    "food_delivery": ["food delivery", "takeaway", "delivery", "ordering food", "fast food", "burgers",
                      "მიტანა", "საჭმლის მიტანა", "ფასტფუდი", "საჭმლის შეკვეთა"],
    "p2p_transfers": ["sending money", "transfers to friends", "lending money", "transfers", "send money to people",
                      "loans to friends", "გადარიცხვა", "ვალი", "სესხება", "მეგობრებზე გადარიცხვა", "ფულის გაგზავნა"],
}
CAT_KEYS = list(CATS.keys())
PREFIX = ["", "i'm ", "today ", "tonight ", "this weekend ", "ამაღამ ", "დღეს ", "no more than 100 on ",
          "max 50 gel for ", "block ", "don't let me spend on ", "არ მომცე ", "მაქსიმუმ 80 ლარი ",
          "limit ", "stop me from ", "cap ", "help me avoid "]
SUFFIX = ["", " tonight", " until morning", " for a week", " დილამდე", " ამ კვირაში", " please",
          " even if i beg", " ok", " მკაცრად", " till 10am"]

def make_commitments(n):
    X, Y = [], []
    for _ in range(n):
        k = 1 if random.random() < 0.8 else 2
        cats = random.sample(CAT_KEYS, k) if random.random() > 0.1 else []
        parts = [random.choice(CATS[c]) for c in cats]
        core = " and ".join(parts) if parts else random.choice(
            ["everything", "anything", "all spending", "total spend", "ყველაფერზე", "სულ", "my card", "money"])
        s = random.choice(PREFIX) + core + random.choice(SUFFIX)
        X.append(noisy(s)); Y.append([1 if c in cats else 0 for c in CAT_KEYS])
    return X, np.array(Y)

cm_X, cm_Y = make_commitments(8000)
cm_vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), lowercase=True, max_features=3000)
cm_M = cm_vec.fit_transform(cm_X)
cm_coef, cm_int = [], []
for j in range(len(CAT_KEYS)):
    c = LogisticRegression(C=6.0, max_iter=2000).fit(cm_M, cm_Y[:, j])
    cm_coef.append(c.coef_[0]); cm_int.append(c.intercept_[0])

class _Stack:  # duck-typed container for export
    def __init__(self, coef, intercept): self.coef_ = np.array(coef); self.intercept_ = np.array(intercept)

# ----------------------------------------------------------------------------------
# 3. Payment risk model (behaviour + context)
# ----------------------------------------------------------------------------------
FEATURES = [
    ("amount_vs_usual", "Amount far above this customer's usual payments"),
    ("new_payee", "First payment to this recipient"),
    ("to_individual", "Transfer to a private person, not a merchant"),
    ("international", "Payment leaves Georgia"),
    ("night_time", "Initiated between 00:00 and 06:00"),
    ("scam_language", "Reference text matches known scam scripts"),
    ("call_in_progress", "Phone call active while paying"),
    ("new_device", "New device or recent password reset"),
    ("young_payee_account", "Recipient account opened < 30 days ago"),
    ("velocity", "Several payments in the last hour"),
    ("share_of_balance", "Large share of available balance"),
]
FEAT_KEYS = [f[0] for f in FEATURES]
AGE_BANDS = ["18-25", "26-40", "41-60", "60+"]

ref_oof = cross_val_predict(LogisticRegression(C=4.0, max_iter=2000), ref_M, ref_y, cv=5, method="predict_proba")[:, 1]
ref_pool_legit = ref_oof[np.array(ref_y) == 0]
ref_pool_scam = ref_oof[np.array(ref_y) == 1]

def gen_payment(scam, age_band):
    b = lambda p: 1.0 if random.random() < p else 0.0
    older = age_band in ("41-60", "60+")
    young = age_band == "18-25"
    if not scam:
        rel = np.random.lognormal(0, 1.0)
        share = random.uniform(0, 0.25)
        big = random.random() < 0.07
        if big:  # rent, laptop, car repair, sending money to family: legit but large
            rel *= random.uniform(6, 50); share = random.uniform(0.25, 0.95)
        f = dict(new_payee=b(0.45 if big else 0.18), to_individual=b(0.40 if older else 0.25), international=b(0.05),
                 night_time=b(0.18 if young else 0.06), call_in_progress=b(0.12 if older else 0.05),
                 new_device=b(0.05), velocity=min(np.random.poisson(0.5) / 5, 1), share=share)
        f["young_payee_account"] = b(0.15) if f["new_payee"] and f["to_individual"] else b(0.02)
        # legit references sometimes contain alarming words ("urgent", "loan") -> scam-like text score
        txt = float(np.random.choice(ref_pool_scam if random.random() < 0.04 else ref_pool_legit))
    else:
        typ = random.choice(["impersonation", "marketplace", "investment", "takeover"])
        rel = {"impersonation": random.uniform(8, 120), "marketplace": random.uniform(1.5, 20),
               "investment": random.uniform(4, 80), "takeover": random.uniform(3, 60)}[typ]
        f = dict(new_payee=b(0.85), to_individual=b(0.8), international=b(0.55 if typ == "investment" else 0.08),
                 night_time=b(0.4 if typ == "takeover" else 0.15),
                 call_in_progress=b(0.7 if typ == "impersonation" else 0.12),
                 new_device=b(0.7 if typ == "takeover" else 0.1), velocity=min(np.random.poisson(1.2) / 5, 1),
                 share=random.uniform(0.05, 0.5) if typ == "marketplace" else random.uniform(0.15, 1.0))
        f["young_payee_account"] = b(0.6)
        txt = float(np.random.choice(ref_pool_scam)) if random.random() < 0.5 else float(np.random.choice(ref_pool_legit))
        if random.random() < 0.15:  # scams that look like ordinary payments (hardest cases)
            rel = np.random.lognormal(0.5, 0.9); f["new_payee"] = b(0.4); f["call_in_progress"] = 0.0
            f["young_payee_account"] = b(0.2); f["share"] = random.uniform(0, 0.3)
            txt = float(np.random.choice(ref_pool_legit))
    x = [float(np.clip(math.log(rel) / math.log(50), -1, 2)), f["new_payee"], f["to_individual"], f["international"],
         f["night_time"], txt, f["call_in_progress"], f["new_device"], f["young_payee_account"], f["velocity"],
         float(np.clip(f["share"], 0, 1))]
    return x

rows, labels, ages = [], [], []
for _ in range(40000):
    age = random.choices(AGE_BANDS, weights=[0.25, 0.4, 0.25, 0.1])[0]
    scam = random.random() < 0.05
    rows.append(gen_payment(scam, age)); labels.append(int(scam)); ages.append(age)
Xr, yr, ages = np.array(rows), np.array(labels), np.array(ages)
Xtr, Xte, ytr, yte, atr, ate = train_test_split(Xr, yr, ages, test_size=0.25, random_state=SEED, stratify=yr)
risk = LogisticRegression(C=1.0, max_iter=3000).fit(Xtr, ytr)
p = risk.predict_proba(Xte)[:, 1]

THRESH = {"nudge": 0.30, "cool_off": 0.60, "bank_review": 0.85}
metrics = {"test_rows": int(len(yte)), "scam_rate": round(float(yte.mean()), 4),
           "roc_auc": round(float(roc_auc_score(yte, p)), 4),
           "pr_auc": round(float(average_precision_score(yte, p)), 4), "thresholds": {}}
for name, t in THRESH.items():
    pred = (p >= t).astype(int)
    metrics["thresholds"][name] = {"threshold": t, "precision": round(float(precision_score(yte, pred, zero_division=0)), 3),
                                   "recall": round(float(recall_score(yte, pred)), 3),
                                   "legit_payments_flagged_pct": round(float(pred[yte == 0].mean() * 100), 2)}
# Fairness audit: age is NOT a model input; we check that false-positive burden is similar across age bands.
fair = {}
for band in AGE_BANDS:
    m = (ate == band) & (yte == 0)
    fair[band] = {"legit_payments": int(m.sum()),
                  "fpr_any_friction_pct": round(float((p[m] >= THRESH["nudge"]).mean() * 100), 2),
                  "fpr_bank_review_pct": round(float((p[m] >= THRESH["bank_review"]).mean() * 100), 3)}
fprs = [v["fpr_any_friction_pct"] for v in fair.values()]
fair_summary = {"max_min_ratio_any_friction": round(max(fprs) / max(min(fprs), 1e-6), 2),
                "rule": "flag for review if any age band carries > 1.5x the friction rate of another"}

models = {
    "version": "pause-models-2026.10.25-r1",
    "trained_on": "synthetic data only (seed %d)" % SEED,
    "reference_text": export_text_model(ref_vec, ref_clf, ["scam_script"]),
    "commitment_categories": export_text_model(cm_vec, _Stack(cm_coef, cm_int), CAT_KEYS),
    "payment_risk": {"features": [{"key": k, "label": l} for k, l in FEATURES],
                     "coef": [round(float(c), 5) for c in risk.coef_[0]],
                     "intercept": round(float(risk.intercept_[0]), 5), "thresholds": THRESH},
}
card = {"version": models["version"], "data": "100%% synthetic. Generator in ml/train.py (seed %d)." % SEED,
        "payment_risk": metrics, "fairness_by_age_band": fair, "fairness_summary": fair_summary,
        "excluded_inputs": ["age", "gender", "ethnicity", "address / district", "nationality", "income level"],
        "reference_text_holdout_accuracy": ref_holdout_acc,
        "coefficients": {k: round(float(c), 3) for k, c in zip(FEAT_KEYS, risk.coef_[0])},
        "limitations": ["Synthetic typologies; must be re-trained and validated on bank data before use",
                        "Base rate in training (5%) is far above real-world fraud rate; thresholds need recalibration",
                        "Reference-text model covers EN/KA templates only"]}
models["model_card"] = card
(ROOT / "app").mkdir(exist_ok=True)
(ROOT / "app" / "models.json").write_text(json.dumps(models, ensure_ascii=False, separators=(",", ":")))
(ROOT / "ml" / "model_card.json").write_text(json.dumps(card, ensure_ascii=False, indent=2))

# parity fixtures for the JS port (checked by ml/verify_port.mjs)
fixtures = {"reference_text": [], "commitment_categories": []}
for s in ["transfer to safe account NOW", "rent october", "ეროვნული ბანკის თანამშრომელი", "dinner split with Luka"]:
    fixtures["reference_text"].append([s, float(ref_clf.predict_proba(ref_vec.transform([s]))[0, 1])])
for s in ["going out tonight max 100 gel on drinks", "no betting this week", "ამაღამ მაქსიმუმ 100 ლარი ბარებში"]:
    M = cm_vec.transform([s])
    fixtures["commitment_categories"].append([s, [float(1 / (1 + math.exp(-(M @ c)[0] - b))) for c, b in zip(cm_coef, cm_int)]])
(ROOT / "ml" / "fixtures.json").write_text(json.dumps(fixtures, ensure_ascii=False, indent=1))
print(json.dumps(card, indent=1, ensure_ascii=False))
