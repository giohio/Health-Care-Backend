"""
CHECK 8 — Deduplication effectiveness
8.1: Samples 500 points and checks for identical text fingerprints (first 100 chars).
8.2: Verifies .seen_hashes.json exists and has a reasonable entry count.

Run from knowledge_base/:
    python checks/check_08_dedup.py
"""

import os
import sys
import json
from pathlib import Path
from collections import Counter

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

from qdrant_client import QdrantClient

client     = QdrantClient(url=os.getenv("QDRANT_URL", "http://localhost:6333"))
COLLECTION = "clinical_guidelines"

# Path to the hashes file — stored inside pipeline/ next to deduplicator.py
HASH_FILE = Path(__file__).parent.parent / "pipeline" / ".seen_hashes.json"

# ── CHECK 8.1 — No duplicate chunks in collection ───────────────────────────
print("=== CHECK 8.1: Deduplication check (sampling 500 points) ===")

points, _ = client.scroll(
    collection_name=COLLECTION,
    limit=500,
    with_payload=True,
    with_vectors=False,
)

# Use first 100 chars of text as fingerprint (full SHA-256 would require more API calls)
fingerprints = [
    (p.payload or {}).get("text", "")[:100].strip()
    for p in points
]
counter  = Counter(fingerprints)
dupes    = {fp: cnt for fp, cnt in counter.items() if cnt > 1 and fp}

if dupes:
    print(f"  [WARN] {len(dupes)} near-duplicate text fingerprint(s) in 500-point sample:")
    for fp, cnt in list(dupes.items())[:5]:
        print(f"    x{cnt}: '{fp[:60]}...'")
    if len(dupes) > 5:
        print(f"    ... and {len(dupes) - 5} more.")
    print("  FIX:   This can happen if .seen_hashes.json was deleted between runs,")
    print("         or if identical source content appears in multiple source files.")
    _qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    print("  If you want a clean slate:")
    print("    1. Delete collection:")
    print("       python -c \"from qdrant_client import QdrantClient; "
          "QdrantClient('" + _qdrant_url + "').delete_collection('clinical_guidelines')\"")
    print("    2. Delete pipeline/.seen_hashes.json")
    print("    3. python run_pipeline.py")
else:
    print(f"  [PASS] No duplicate text fingerprints found in {len(points)}-point sample.")

# ── CHECK 8.2 — .seen_hashes.json health ────────────────────────────────────
print("\n=== CHECK 8.2: .seen_hashes.json file ===")

if HASH_FILE.exists():
    try:
        hashes = json.loads(HASH_FILE.read_text(encoding="utf-8"))
        total_count = client.count(collection_name=COLLECTION, exact=True).count
        print(f"  [INFO] .seen_hashes.json has {len(hashes)} entries.")
        print(f"  [INFO] Collection has {total_count} points.")
        if len(hashes) < total_count * 0.8:
            print("  [WARN] Hash count is much lower than point count.")
            print("         The hash file may have been partially reset.")
            print("         Re-running pipeline may re-upsert chunks (Qdrant handles idempotently).")
        elif len(hashes) >= total_count:
            print("  [PASS] Hash count ≥ point count — dedup coverage looks good.")
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  [WARN] Could not read .seen_hashes.json: {exc}")
        print("  FIX:   Delete the file and re-run pipeline to regenerate it.")
else:
    print(f"  [WARN] .seen_hashes.json not found at: {HASH_FILE}")
    print("         This means the next run will re-process and re-embed all files.")
    print("         The pipeline will still work, but will take longer.")
    print("  NOTE:  The file is created automatically on first pipeline run.")

# ── CHECK 8.3 — Source file count vs hash count (sanity) ────────────────────
print("\n=== CHECK 8.3: Source file count sanity ===")

rag_dir = Path(__file__).parent.parent.parent / "rag_knowledge_base"
if rag_dir.exists():
    md_files = list(rag_dir.rglob("*.md"))
    print(f"  Source .md files in rag_knowledge_base/: {len(md_files)}")
    if len(md_files) == 0:
        print("  [FAIL] No .md files found — nothing to process.")
    else:
        print(f"  [INFO] With {len(md_files)} files, expected several hundred to several thousand chunks.")
else:
    print("  [WARN] ../rag_knowledge_base/ directory not found.")
    print(f"         Expected at: {rag_dir}")
