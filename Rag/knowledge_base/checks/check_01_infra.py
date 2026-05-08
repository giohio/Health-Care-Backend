"""
CHECK 1 — Infrastructure health
Verifies Qdrant is reachable + collection exists, and Ollama returns 768-dim vectors.

Run from knowledge_base/:
    python checks/check_01_infra.py
"""

import os
import sys
from pathlib import Path

# Allow imports from knowledge_base/ root
sys.path.insert(0, str(Path(__file__).parent.parent))

import ollama
from dotenv import load_dotenv
from qdrant_client import QdrantClient

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

COLLECTION  = "clinical_guidelines"
VECTOR_DIM  = 768
QDRANT_URL  = os.getenv("QDRANT_URL",  "http://localhost:6333")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
_ollama     = ollama.Client(host=OLLAMA_HOST)

# ── CHECK 1.1 — Qdrant ──────────────────────────────────────────────────────
print("=== CHECK 1.1: Qdrant health ===")
import time

_qdrant_ok = False
for _attempt in range(3):
    try:
        client = QdrantClient(url=QDRANT_URL)
        info   = client.get_collection(COLLECTION)
        count  = info.points_count
        _qdrant_ok = True
        break
    except Exception as _exc:
        _last_exc = _exc
        if _attempt < 2:
            time.sleep(2)

if not _qdrant_ok:
    exc = _last_exc
    print(f"  [FAIL] Qdrant not reachable or collection missing: {exc}")
    exc_str = str(exc)
    if "10061" in exc_str or "refused" in exc_str.lower():
        print("  HINT: Running Docker inside WSL (not Docker Desktop)?")
        print("    Option A — run Python inside WSL too:")
        print("               wsl python checks/run_all_checks.py")
        print("    Option B — create knowledge_base/.env with the WSL IP:")
        print("               $ wsl hostname -I   # e.g. 172.22.80.1")
        print("               QDRANT_URL=http://172.22.80.1:6333")
        print("               OLLAMA_HOST=http://172.22.80.1:11434")
    else:
        print("  FIX: docker compose up -d && python run_pipeline.py")
    sys.exit(1)

print(f"  [PASS] Qdrant reachable. Collection '{COLLECTION}' has {count} points.")
if count == 0:
    print("  [FAIL] Collection exists but has 0 points — pipeline has not been run yet.")
    print("  FIX: python run_pipeline.py")
    sys.exit(1)
if count < 5000:
    print(f"  [WARN] Only {count} points. Expected >5000 for all 7 source types.")
    print("         Possible causes: not all dept folders processed, chunking too")
    print("         aggressive, or deduplicator dropped too much.")

# ── CHECK 1.2 — Ollama / nomic-embed-text ───────────────────────────────────
print("\n=== CHECK 1.2: Ollama + nomic-embed-text health ===")
try:
    resp = _ollama.embed(model="nomic-embed-text", input=["test medical term"])
    vec  = resp.embeddings[0]
    assert len(vec) == VECTOR_DIM, f"Expected {VECTOR_DIM} dims, got {len(vec)}"
    print(f"  [PASS] nomic-embed-text returns {len(vec)}-dim vectors.")
except Exception as exc:
    print(f"  [FAIL] Ollama/embedding not working: {exc}")
    print("  FIX: docker exec -it ollama ollama pull nomic-embed-text")
    sys.exit(1)
