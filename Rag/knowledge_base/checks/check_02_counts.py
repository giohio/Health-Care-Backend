"""
CHECK 2 — Point count per department
Every department must have ≥ 200 points.
Fewer than that means source files weren't processed or chunking was too aggressive.

Run from knowledge_base/:
    python checks/check_02_counts.py
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

client     = QdrantClient(url=os.getenv("QDRANT_URL", "http://localhost:6333"))
COLLECTION = "clinical_guidelines"

DEPARTMENTS = [
    "respiratory",
    "dermatology",
    "neurology",
    "ophthalmology",
    "cardiology",
    "nephrology",
    "hematology",
    "endocrinology",
]

# Expected rough ranges for reference (informational only):
EXPECTED_RANGES = {
    "respiratory":   (800,  2000),
    "dermatology":   (600,  1500),
    "neurology":     (400,  1000),
    "ophthalmology": (300,   800),
    "cardiology":    (500,  1200),
    "nephrology":    (400,   900),
    "hematology":    (300,   700),
    "endocrinology": (300,   700),
}

MIN_POINTS_PER_DEPT = 200

print("=== CHECK 2.1: Points per department ===\n")
all_pass = True

for dept in DEPARTMENTS:
    result = client.count(
        collection_name=COLLECTION,
        count_filter=Filter(
            must=[FieldCondition(key="department", match=MatchValue(value=dept))]
        ),
        exact=True,
    )
    count  = result.count
    lo, hi = EXPECTED_RANGES.get(dept, (MIN_POINTS_PER_DEPT, 99999))
    status = "PASS" if count >= MIN_POINTS_PER_DEPT else "FAIL"

    range_note = ""
    if count >= MIN_POINTS_PER_DEPT and count < lo:
        range_note = f"  (below expected range {lo}–{hi}, but above minimum)"
    elif count > hi:
        range_note = f"  (above expected range {lo}–{hi} — may be fine)"

    if status == "FAIL":
        all_pass = False

    print(f"  [{status}] {dept:<20} {count:>6} points  "
          f"(min: {MIN_POINTS_PER_DEPT}, expected: {lo}–{hi}){range_note}")

if not all_pass:
    print("\n  FIX for low-count departments:")
    print("  1. Check knowledge_base/../rag_knowledge_base/<dept>/*.md files exist")
    print("  2. Run: python -c \"from pipeline.classifier import classify_file; "
          "from pathlib import Path; "
          "print(classify_file(Path('../rag_knowledge_base/<dept>/sample.md')))\"")
    print("  3. Fix classifier.py if department mapping is wrong")
    print("  4. Re-run: python run_pipeline.py  (dedup skips already-loaded chunks)")
else:
    print(f"\n  [PASS] All {len(DEPARTMENTS)} departments meet the minimum threshold.")

# Also print total
total = client.count(collection_name=COLLECTION, exact=True).count
print(f"\n  Total points in collection: {total}")
