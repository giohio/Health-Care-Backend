"""
CHECK 7 — Table chunk integrity
7.1: Verifies table chunks are not split mid-row (must have header + separator + ≥1 data row).
7.2: Verifies table chunks have a context prefix (page_title / section_heading before the table).

Run from knowledge_base/:
    python checks/check_07_tables.py
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

# ── CHECK 7.1 — Table chunk structure ──────────────────────────────────────
print("=== CHECK 7.1: Table chunk integrity ===")

table_points, _ = client.scroll(
    collection_name=COLLECTION,
    scroll_filter=Filter(
        must=[FieldCondition(key="chunk_type", match=MatchValue(value="table"))]
    ),
    limit=50,
    with_payload=True,
    with_vectors=False,
)

total_table_points = client.count(
    collection_name=COLLECTION,
    count_filter=Filter(
        must=[FieldCondition(key="chunk_type", match=MatchValue(value="table"))]
    ),
    exact=True,
).count

if not table_points:
    print("  [FAIL] No table chunks found in the collection.")
    print("  FIX:   Verify that nephrology_endocrinology / hematology_internal .md files")
    print("         contain markdown tables using | col | format (not HTML).")
    print("         If HTML: convert with pandoc: pandoc -f html -t gfm input.html -o output.md")
else:
    print(f"  Found {total_table_points} total table chunks. Inspecting {len(table_points)} sample.")

    broken_short: list[tuple]   = []  # less than 3 table lines
    broken_nosep: list[tuple]   = []  # missing separator row (---|---)

    for p in table_points:
        text  = (p.payload or {}).get("text", "")
        lines = text.strip().split("\n")

        # Count lines that look like table rows
        table_lines = [ln for ln in lines if ln.strip().startswith("|")]
        has_separator = any(
            set(ln.replace("|", "").replace("-", "").replace(":", "").replace(" ", "")) == set()
            or "---" in ln
            for ln in lines
        )

        if len(table_lines) < 3:
            broken_short.append((p.id, text[:120]))
        if not has_separator:
            broken_nosep.append((p.id, text[:80]))

    if broken_short:
        print(f"  [FAIL] {len(broken_short)} table chunk(s) have fewer than 3 table rows:")
        for pid, preview in broken_short[:3]:
            print(f"    ID {pid}: {preview!r}")
        print("  FIX:   Review TABLE_PATTERN regex in pipeline/chunkers/table_aware.py.")
    else:
        print(f"  [PASS] All {len(table_points)} sampled table chunks have ≥ 3 table rows.")

    if broken_nosep:
        print(f"  [FAIL] {len(broken_nosep)} table chunk(s) have no separator row (---|---):")
        for pid, preview in broken_nosep[:3]:
            print(f"    ID {pid}: {preview!r}")
        print("  FIX:   The source table may not use standard GFM syntax.")
        print("         Inspect the raw .md file and fix the table format, then re-run.")
    else:
        print(f"  [PASS] All {len(table_points)} sampled table chunks have a separator row.")

# ── CHECK 7.2 — Context prefix present ─────────────────────────────────────
print("\n=== CHECK 7.2: Table chunks have context prefix ===")

no_context: list = []
has_context: int = 0

for p in table_points[:20]:
    text = (p.payload or {}).get("text", "")
    lines = [ln for ln in text.strip().split("\n") if ln.strip()]
    if not lines:
        continue

    first_line          = lines[0]
    first_table_line    = next(
        (ln for ln in lines if ln.strip().startswith("|")), ""
    )

    if first_line.strip() == first_table_line.strip():
        # The very first line IS the header row — no context prefix
        no_context.append(p.id)
    else:
        has_context += 1

if no_context:
    print(f"  [WARN] {len(no_context)} table chunk(s) have no context prefix "
          f"(starts directly with header row):")
    for pid in no_context[:3]:
        print(f"    ID {pid}")
    print("  This reduces retrieval quality when queries mention the table topic.")
    print("  FIX:   Verify chunk_table_aware() in run_pipeline.py receives page_title.")
    print("         Check table_aware.py prefix assembly logic.")
else:
    print(f"  [PASS] All {len(table_points[:20])} sampled table chunks have a context prefix.")

# ── CHECK 7.3 — Tables present in expected departments ─────────────────────
print("\n=== CHECK 7.3: Table chunks by department ===")

for dept in ["nephrology", "hematology", "endocrinology"]:
    from qdrant_client.models import MatchAny
    result = client.count(
        collection_name=COLLECTION,
        count_filter=Filter(
            must=[
                FieldCondition(key="chunk_type",  match=MatchValue(value="table")),
                FieldCondition(key="department",   match=MatchValue(value=dept)),
            ]
        ),
        exact=True,
    )
    status = "PASS" if result.count > 0 else "WARN"
    print(f"  [{status}] {dept:<22} {result.count:>4} table chunks")

if total_table_points < 10:
    print("\n  [WARN] Very low total table count. Lab reference & CKD staging files")
    print("         may not have been classified correctly for table_aware chunking.")
