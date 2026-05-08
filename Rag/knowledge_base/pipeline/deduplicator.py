"""
Hash-based deduplication before embedding.
Prevents duplicate chunks from being upserted on re-runs of the pipeline.
Seen hashes are persisted to disk so incremental runs skip known content.
"""

import hashlib
import json
from pathlib import Path
from typing import List, Tuple

import numpy as np


SEEN_HASHES_FILE = Path(__file__).parent / ".seen_hashes.json"


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def load_seen_hashes() -> set:
    if SEEN_HASHES_FILE.exists():
        try:
            return set(json.loads(SEEN_HASHES_FILE.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            return set()
    return set()


def save_seen_hashes(hashes: set) -> None:
    SEEN_HASHES_FILE.write_text(
        json.dumps(sorted(hashes)), encoding="utf-8"
    )


def deduplicate(
    chunks_with_payloads: List[Tuple[str, np.ndarray, dict]],
) -> List[Tuple]:
    """
    Input:  list of (chunk_id_hex, vector_np, payload_dict)
    Output: filtered list — no two entries share the same content hash.
    Persists new hashes to disk for incremental runs.
    """
    seen      = load_seen_hashes()
    unique    = []
    new_hashes: set = set()

    for chunk_id, vector, payload in chunks_with_payloads:
        h = content_hash(payload["text"])
        if h not in seen:
            unique.append((chunk_id, vector, payload))
            new_hashes.add(h)

    seen.update(new_hashes)
    save_seen_hashes(seen)

    skipped = len(chunks_with_payloads) - len(unique)
    if skipped:
        print(f"[INFO] Dedup: skipped {skipped} duplicate chunks")

    return unique
