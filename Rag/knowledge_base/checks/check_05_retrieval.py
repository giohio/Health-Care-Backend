"""
CHECK 5 — Retrieval quality (the most important check)
20 queries across all 8 departments.
Pass criterion: keyword present AND correct department in top-3 results, ≥ 85 % of queries.

Run from knowledge_base/:
    python checks/check_05_retrieval.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from retriever.retriever import retrieve

# ── Test suite ──────────────────────────────────────────────────────────────
# (query_text, expected_department, keyword_that_must_appear_in_top-3_text)
TEST_QUERIES = [
    # Respiratory
    ("lobar pneumonia right lobe air bronchogram treatment antibiotics", "respiratory", "pneumonia"),
    ("asthma exacerbation bronchospasm wheeze treatment salbutamol",     "respiratory", "asthma"),
    ("bronchopneumonia patchy bilateral opacities chest radiograph",     "respiratory", "bilateral"),

    # Dermatology
    ("ABCDE criteria asymmetry border color diameter",                   "dermatology", "melanoma"),
    ("melanoma dermoscopy asymmetry irregular border color variation",   "dermatology", "melanoma"),
    ("basal cell carcinoma pearly nodule rolled border", "dermatology",   "basal"),

    # Neurology
    ("glioblastoma ring enhancement MRI brain",          "neurology",     "glioblastoma"),
    ("intra-axial brain tumor WHO grade classification", "neurology",     "tumor"),

    # Ophthalmology
    ("non-proliferative diabetic retinopathy fundus",    "ophthalmology", "retinopathy"),
    ("diabetic macular edema OCT central thickness",     "ophthalmology", "macular"),

    # Cardiology
    ("atrial fibrillation irregularly irregular pulse",           "cardiology",  "atrial"),
    ("left bundle branch block LBBB wide QRS morphology criteria","cardiology",  "bundle"),
    ("ventricular tachycardia wide complex QRS DC cardioversion", "cardiology",  "tachycardia"),

    # Nephrology
    ("GFR 45 albuminuria CKD stage 3a classification",   "nephrology",    "ckd"),
    ("eGFR decline progression kidney disease KDIGO",    "nephrology",    "egfr"),

    # Hematology
    ("MCV 72 microcytic hypochromic iron deficiency",    "hematology",    "iron"),
    ("low hemoglobin 10.2 anemia CBC interpretation",    "hematology",    "anemia"),
    ("platelet count 142 mild thrombocytopenia causes",  "hematology",    "platelet"),

    # Endocrinology
    ("HbA1c 7.8 glycemic control target ADA standard",  "endocrinology", "hba1c"),
    ("type 2 diabetes metformin first line therapy",     "endocrinology", "metformin"),
]

print("=== CHECK 5.1: Retrieval quality (20 queries) ===\n")

passed: int = 0
failed: list[tuple] = []

for query, dept, keyword in TEST_QUERIES:
    try:
        results = retrieve(query, department=dept, top_k=3)
    except Exception as exc:
        print(f"  [ERROR] {dept:<18} | {query[:45]}")
        print(f"          Exception: {exc}")
        failed.append((query, dept, keyword, f"exception: {exc}"))
        continue

    combined      = " ".join((r.get("text") or "").lower() for r in results)
    keyword_found = keyword.lower() in combined
    dept_ok       = all(r.get("dept") == dept for r in results) if results else False

    if keyword_found and dept_ok:
        passed += 1
        print(f"  [PASS] {dept:<18} | {query[:45]}")
    else:
        reasons: list[str] = []
        if not keyword_found:
            reasons.append(f"keyword '{keyword}' not in top-3")
        if not dept_ok:
            actual_depts = list({r.get("dept") for r in results})
            reasons.append(f"dept mismatch (got {actual_depts})")
        if not results:
            reasons.append("no results returned")

        print(f"  [FAIL] {dept:<18} | {query[:45]}")
        print(f"         Reason: {', '.join(reasons)}")
        if results:
            top_text = (results[0].get("text") or "")[:110]
            print(f"         Top-1 preview: {top_text}...")
        failed.append((query, dept, keyword, ", ".join(reasons)))

total = len(TEST_QUERIES)
pct   = (passed / total) * 100

print(f"\n{'='*62}")
print(f"Score: {passed}/{total} = {pct:.1f}%")

if pct >= 85.0:
    print("RESULT: [PASS] — Knowledge base quality is sufficient.")
    print("Safe to wire to AI service.")
else:
    print("RESULT: [FAIL] — Do NOT wire to AI service yet.")
    print(f"\nFailed queries ({len(failed)}):")
    for q, d, kw, reason in failed:
        print(f"  dept={d:<18} keyword={kw:<20} {reason}")

    print("\nDiagnosis guide:")
    print("  keyword not found -> chunk too small, or synonym mismatch")
    print("                      FIX: add synonym to metadata.py _DISEASE_MAP")
    print("  dept mismatch     -> classifier.py mis-labelled source file")
    print("                      FIX: verify classify_file() for that source's URL/slug")
    print("  exception         -> retriever.py filter or Qdrant connectivity issue")
