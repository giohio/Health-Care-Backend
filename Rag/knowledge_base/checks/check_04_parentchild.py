"""
CHECK 4 — Chunk structure integrity
4.1: Every child chunk's parent_id resolves to a real point in Qdrant.
4.2: chunk_type distribution looks healthy.

IMPORTANT implementation note:
  parent_id in the payload is a 16-char hex string (e.g. "a3f9b1c2d4e5f607").
  Qdrant point IDs are uint64 integers (stored as int(hex, 16)).
  We must convert before calling client.retrieve().

Run from knowledge_base/:
    python checks/check_04_parentchild.py
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

# ── CHECK 4.1 — Parent-child link integrity ─────────────────────────────────
print("=== CHECK 4.1: Parent-child link integrity ===")

# Collect unique parent_id values from child chunks (scroll up to 20 batches)
all_parent_ids: set[str] = set()
offset     = None
batch_count = 0
MAX_BATCHES = 20

while batch_count < MAX_BATCHES:
    points, next_offset = client.scroll(
        collection_name=COLLECTION,
        scroll_filter=Filter(
            must=[FieldCondition(key="chunk_type", match=MatchValue(value="child"))]
        ),
        limit=100,
        offset=offset,
        with_payload=True,
        with_vectors=False,
    )
    for p in points:
        pid = (p.payload or {}).get("parent_id")
        if pid:
            all_parent_ids.add(pid)
    if next_offset is None:
        break
    offset = next_offset
    batch_count += 1

total_parent_refs = len(all_parent_ids)
print(f"  Scanning up to {MAX_BATCHES} batches of child chunks...")
print(f"  Found {total_parent_refs} unique parent_id references.")

if total_parent_refs == 0:
    print("  [WARN] No child chunks found at all.")
    print("         Either: hierarchical chunking produced no children,")
    print("         or no Radiopaedia/StatPearls files were processed.")
else:
    # Verify up to 500 parent IDs actually exist in Qdrant
    sample_ids = list(all_parent_ids)[:500]
    missing: list[str] = []

    for hex_id in sample_ids:
        try:
            # Convert hex string → uint64 (how we store point IDs in Qdrant)
            uint_id = int(hex_id, 16)
            results = client.retrieve(
                collection_name=COLLECTION,
                ids=[uint_id],
                with_payload=False,
                with_vectors=False,
            )
            if not results:
                missing.append(hex_id)
        except Exception as exc:
            missing.append(f"{hex_id} (error: {exc})")

    if not missing:
        print(f"  [PASS] All {len(sample_ids)} sampled parent_id references resolve "
              f"to existing points.")
    else:
        print(f"  [FAIL] {len(missing)} parent IDs not found in Qdrant "
              f"(out of {len(sample_ids)} checked):")
        for mid in missing[:3]:
            print(f"    {mid}")
        print("  FIX: Parent chunk was not upserted, or its ID changed between runs.")
        print("  Check that chunk_hierarchical() and upsert_chunks() are in same pipeline run.")

# ── CHECK 4.2 — chunk_type distribution ─────────────────────────────────────
print("\n=== CHECK 4.2: chunk_type distribution ===")

type_counts: dict[str, int] = {}
for ctype in ["parent", "child", "sentence_group", "fixed", "table"]:
    result = client.count(
        collection_name=COLLECTION,
        count_filter=Filter(
            must=[FieldCondition(key="chunk_type", match=MatchValue(value=ctype))]
        ),
        exact=True,
    )
    type_counts[ctype] = result.count
    print(f"  {ctype:<20} {result.count:>7} points")

print()
total = sum(type_counts.values())
print(f"  Total indexed chunk types: {total}")

# Semantic evaluation of the distribution
if type_counts.get("child", 0) == 0:
    print("  [WARN] No child chunks found — hierarchical chunker may not have run.")
if type_counts.get("table", 0) == 0:
    print("  [WARN] No table chunks found.")
    print("         Check that nephrology_endocrinology/*.md files contain | col | tables.")
if type_counts.get("sentence_group", 0) == 0:
    print("  [WARN] No sentence_group chunks — semantic chunker may not have run.")
    print("         Check dermatology/ophthalmology files are classified as 'semantic'.")
if type_counts.get("child", 0) > type_counts.get("parent", 0):
    print("  [PASS] child > parent (expected — each parent generates multiple children).")
elif type_counts.get("parent", 0) > 0:
    print("  [WARN] parent count exceeds child count — unexpected for hierarchical chunking.")
