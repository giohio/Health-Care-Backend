"""
CHECK 6 — Vector quality
Samples 50 vectors and verifies:
  6.1 — No zero vectors (embedding failures silently produce np.zeros)
  6.2 — Vectors are diverse (high avg similarity = embedding model stuck)
  6.3 — All vectors are 768-dim

Run from knowledge_base/:
    python checks/check_06_vectors.py
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

import numpy as np
from qdrant_client import QdrantClient

client     = QdrantClient(url=os.getenv("QDRANT_URL", "http://localhost:6333"))
COLLECTION = "clinical_guidelines"

print("=== CHECK 6.1: Vector quality (sampling 50 points) ===")

points, _ = client.scroll(
    collection_name=COLLECTION,
    limit=50,
    with_payload=False,
    with_vectors=True,
)

if not points:
    print("  [FAIL] No points found in collection — pipeline may not have run.")
    sys.exit(1)

vectors = [np.array(p.vector, dtype=np.float32) for p in points]

# ── TEST 1: No zero vectors ─────────────────────────────────────────────────
zero_vecs = [v for v in vectors if np.linalg.norm(v) < 0.01]
if zero_vecs:
    print(f"  [FAIL] {len(zero_vecs)}/{len(vectors)} zero vectors found.")
    print("         These chunks failed to embed — embedder.py fallback np.zeros triggered.")
    print("  FIX:   Restart Ollama, verify nomic-embed-text is loaded, re-run pipeline.")
    print("         (Delete collection first to force re-embedding of affected chunks.)")
else:
    print(f"  [PASS] No zero vectors found in {len(vectors)}-point sample.")

# ── TEST 2: Vector diversity (consecutive cosine similarity) ─────────────────
print("\n=== CHECK 6.2: Vector diversity ===")
if len(vectors) >= 2:
    sims: list[float] = []
    for i in range(min(20, len(vectors) - 1)):
        a, b = vectors[i], vectors[i + 1]
        norm_product = np.linalg.norm(a) * np.linalg.norm(b)
        if norm_product > 0:
            cos = float(np.dot(a, b) / norm_product)
            sims.append(cos)

    if sims:
        avg_sim = float(np.mean(sims))
        min_sim = float(np.min(sims))
        max_sim = float(np.max(sims))

        if avg_sim > 0.99:
            print(f"  [FAIL] Avg consecutive cosine similarity = {avg_sim:.4f}")
            print("         Vectors are near-identical — embedding model returned same output.")
            print("  FIX:   docker restart ollama")
            print("         docker exec -it ollama ollama pull nomic-embed-text")
            print("         Delete collection and re-run pipeline.")
        elif avg_sim > 0.90:
            print(f"  [WARN] High avg cosine similarity = {avg_sim:.4f}  "
                  f"(min={min_sim:.3f}, max={max_sim:.3f})")
            print("         Could be OK if sample is all from the same document.")
            print("         Check variety across departments.")
        else:
            print(f"  [PASS] Avg consecutive cosine similarity = {avg_sim:.4f}  "
                  f"(min={min_sim:.3f}, max={max_sim:.3f}) — healthy diversity.")
    else:
        print("  [WARN] Could not compute similarities (zero-norm vectors in sample).")
else:
    print("  [WARN] Too few vectors to compute diversity.")

# ── TEST 3: Dimension check ─────────────────────────────────────────────────
print("\n=== CHECK 6.3: Vector dimensions ===")
wrong_dim = [v for v in vectors if len(v) != 768]
if wrong_dim:
    actual_dims = sorted({len(v) for v in wrong_dim})
    print(f"  [FAIL] {len(wrong_dim)} vectors with wrong dimension: {actual_dims}")
    print("         Expected 768 (nomic-embed-text). Wrong model may be loaded.")
    print("  FIX:   docker exec -it ollama ollama list")
    print("         Confirm 'nomic-embed-text' is listed, not another model.")
else:
    print(f"  [PASS] All {len(vectors)} sampled vectors are 768-dim.")

# ── TEST 4: Norm distribution (healthy vectors cluster near 1.0 for cosine) ─
print("\n=== CHECK 6.4: L2-norm distribution ===")
norms = [float(np.linalg.norm(v)) for v in vectors]
avg_norm = float(np.mean(norms))
min_norm = float(np.min(norms))
max_norm = float(np.max(norms))
print(f"  L2-norm: avg={avg_norm:.4f}, min={min_norm:.4f}, max={max_norm:.4f}")
if min_norm < 0.1:
    print("  [WARN] Some very low-norm vectors present — possible embedding failures.")
else:
    print("  [PASS] Norm distribution looks healthy.")
