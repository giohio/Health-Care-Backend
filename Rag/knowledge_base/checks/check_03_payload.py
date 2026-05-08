"""
CHECK 3 — Payload completeness
Samples 200 points and verifies all required metadata fields are present
and that department values are valid canonical strings.

Run from knowledge_base/:
    python checks/check_03_payload.py
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

from qdrant_client import QdrantClient

client     = QdrantClient(url=os.getenv("QDRANT_URL", "http://localhost:6333"))
COLLECTION = "clinical_guidelines"

REQUIRED_FIELDS = [
    "department",
    "disease_category",
    "source",
    "chunk_type",
    "page_title",
    "text",
    "char_count",
    "token_estimate",
]

VALID_DEPARTMENTS = {
    "respiratory", "dermatology", "neurology", "ophthalmology",
    "cardiology", "nephrology", "hematology", "endocrinology",
    "internal_medicine",
}

VALID_CHUNK_TYPES = {"parent", "child", "sentence_group", "fixed", "table"}

# ── CHECK 3.1 — Required fields present ────────────────────────────────────
print("=== CHECK 3.1: Payload completeness (sampling 200 points) ===")

points, _ = client.scroll(
    collection_name=COLLECTION,
    limit=200,
    with_payload=True,
    with_vectors=False,
)

if not points:
    print("  [FAIL] No points in collection — pipeline has not been run yet.")
    sys.exit(1)

missing_report: dict[str, int] = {}
empty_report:   dict[str, int] = {}

for point in points:
    pl = point.payload or {}
    for field in REQUIRED_FIELDS:
        if field not in pl or pl[field] is None:
            missing_report[field] = missing_report.get(field, 0) + 1
        elif field == "text" and str(pl[field]).strip() == "":
            empty_report[field] = empty_report.get(field, 0) + 1

if not missing_report and not empty_report:
    print(f"  [PASS] All 200 sampled points have all {len(REQUIRED_FIELDS)} required fields.")
else:
    for field, count in missing_report.items():
        print(f"  [FAIL] Field '{field}' missing/null in {count}/200 sampled points.")
    for field, count in empty_report.items():
        print(f"  [FAIL] Field '{field}' is empty string in {count}/200 sampled points.")
    print("\n  FIX: Review pipeline/metadata.py build_payload().")
    print("  Ensure every chunker call in run_pipeline.py passes all required args.")
    print("  Re-run: python run_pipeline.py")

# ── CHECK 3.2 — Department values are valid ─────────────────────────────────
print("\n=== CHECK 3.2: Department values are valid ===")

invalid_dept_points: list[tuple] = []
dept_value_counts: dict[str, int] = {}

for point in points:
    dept = (point.payload or {}).get("department", "")
    dept_value_counts[dept] = dept_value_counts.get(dept, 0) + 1
    if dept not in VALID_DEPARTMENTS:
        invalid_dept_points.append((point.id, dept))

if not invalid_dept_points:
    print("  [PASS] All 200 sampled points have valid department values.")
else:
    print(f"  [FAIL] {len(invalid_dept_points)} point(s) with invalid department:")
    for pid, dept in invalid_dept_points[:5]:
        print(f"    Point {pid}: department='{dept}'")
    if len(invalid_dept_points) > 5:
        print(f"    ... and {len(invalid_dept_points) - 5} more.")
    print("  FIX: Review pipeline/classifier.py _normalize_department().")

print("  Department value distribution in sample:")
for dept, cnt in sorted(dept_value_counts.items(), key=lambda x: -x[1]):
    valid_mark = "" if dept in VALID_DEPARTMENTS else " ← INVALID"
    print(f"    {dept:<22} {cnt:>4}{valid_mark}")

# ── CHECK 3.3 — Chunk types are valid ───────────────────────────────────────
print("\n=== CHECK 3.3: Chunk type distribution ===")

chunk_type_counts: dict[str, int] = {}
invalid_chunk_type_points: list[tuple] = []

for point in points:
    ctype = (point.payload or {}).get("chunk_type", "")
    chunk_type_counts[ctype] = chunk_type_counts.get(ctype, 0) + 1
    if ctype not in VALID_CHUNK_TYPES:
        invalid_chunk_type_points.append((point.id, ctype))

if not invalid_chunk_type_points:
    print("  [PASS] All chunk_type values are valid.")
else:
    print(f"  [FAIL] {len(invalid_chunk_type_points)} invalid chunk_type values:")
    for pid, ct in invalid_chunk_type_points[:3]:
        print(f"    Point {pid}: chunk_type='{ct}'")

print("  Chunk type distribution in sample:")
for ct, cnt in sorted(chunk_type_counts.items(), key=lambda x: -x[1]):
    print(f"    {ct:<20} {cnt:>4}")

# ── CHECK 3.4 — No trivially short text ─────────────────────────────────────
print("\n=== CHECK 3.4: Minimum text length ===")

short_chunks = [p for p in points if len((p.payload or {}).get("text", "")) < 50]
if not short_chunks:
    print("  [PASS] No chunks with text < 50 chars in sample.")
else:
    print(f"  [WARN] {len(short_chunks)} chunk(s) with text < 50 chars found.")
    for p in short_chunks[:3]:
        print(f"    ID {p.id}: '{(p.payload or {}).get('text', '')}'")
    print("  FIX: Verify length guards are active in each chunker (>50 char minimum).")
