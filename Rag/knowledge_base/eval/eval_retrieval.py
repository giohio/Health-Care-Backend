"""
Retrieval quality gate — 20 test queries across all departments.
Pass criterion: correct department chunk in top-3 results ≥ 85 % of queries.

Run:
    cd "AI Service/knowledge_base"
    python eval/eval_retrieval.py
"""

import sys
from pathlib import Path

# Make the knowledge_base package root importable
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from retriever.retriever import retrieve

# ── Test suite ──────────────────────────────────────────────────────────────
# (query_text, expected_department, keyword_that_must_appear_in_top-3_text)
TEST_QUERIES = [
    # Respiratory
    ("consolidation right lower lobe opacity",         "respiratory",   "pneumonia"),
    ("bilateral hilar lymphadenopathy chest xray",     "respiratory",   "pulmonary"),
    ("systematic approach reading chest x-ray",        "respiratory",   "chest"),
    # Dermatology
    ("ABCDE criteria asymmetry border color diameter", "dermatology",   "melanoma"),
    ("dermoscopy pigment network atypical",            "dermatology",   "melanoma"),
    ("pearly nodule telangiectasia skin lesion",       "dermatology",   "basal"),
    # Neurology
    ("glioblastoma ring enhancement MRI WHO grade 4",  "neurology",     "glioblastoma"),
    ("intra-axial brain tumor differential diagnosis", "neurology",     "glioma"),
    # Ophthalmology
    ("non-proliferative diabetic retinopathy fundus",  "ophthalmology", "retinopathy"),
    ("diabetic macular edema OCT findings",            "ophthalmology", "macular"),
    # Cardiology
    ("atrial fibrillation irregularly irregular QRS",  "cardiology",    "fibrillation"),
    ("left bundle branch block LBBB ECG criteria",     "cardiology",    "bundle"),
    ("ventricular tachycardia wide complex rhythm",    "cardiology",    "tachycardia"),
    # Nephrology
    ("GFR 45 albuminuria CKD stage classification",   "nephrology",    "ckd"),
    ("eGFR progression chronic kidney disease KDIGO",  "nephrology",    "kidney"),
    # Hematology
    ("MCV 72 microcytic anemia iron deficiency CBC",   "hematology",    "anemia"),
    ("low hemoglobin CBC interpretation",              "hematology",    "hemoglobin"),
    ("platelet count 142 thrombocytopenia mild",       "hematology",    "platelet"),
    # Endocrinology
    ("HbA1c 7.8 glycemic target ADA type 2 diabetes", "endocrinology", "diabetes"),
    ("type 2 diabetes metformin first line treatment", "endocrinology", "metformin"),
]

# ── Evaluation runner ───────────────────────────────────────────────────────

def run_eval() -> None:
    passed = 0
    total  = len(TEST_QUERIES)

    for query, dept, keyword in TEST_QUERIES:
        try:
            results = retrieve(query, department=dept, top_k=3)
        except Exception as exc:
            print(f"  [ERROR] {dept} | {query[:50]}")
            print(f"          {exc}")
            continue

        combined_text = " ".join((r.get("text") or "").lower() for r in results)
        keyword_hit   = keyword.lower() in combined_text
        dept_ok       = all(r.get("dept") == dept for r in results[:3]) if results else False

        if keyword_hit and dept_ok:
            passed += 1
            print(f"  [PASS] {dept:15s} | {query[:55]}")
        else:
            print(f"  [FAIL] {dept:15s} | {query[:55]}")
            print(f"         keyword '{keyword}' found: {keyword_hit}  |  dept correct: {dept_ok}")
            if results:
                print(f"         top-1 text: {results[0].get('text', '')[:120]}")

    pct = (passed / total) * 100
    print(f"\nResult: {passed}/{total} = {pct:.1f}%")

    if pct >= 85.0:
        print("PASS — Knowledge base quality is sufficient. Wire to AI service.")
    else:
        print("FAIL — Fix chunking or metadata before wiring to AI service.")
        print("Common causes: wrong department tag, chunks too small,")
        print("               keyword missing from content, table rows split.")


if __name__ == "__main__":
    run_eval()
