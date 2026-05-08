"""
Embeds text chunks using nomic-embed-text via a local Ollama server.
Processes text in batches to stay within memory limits.
Falls back to zero vectors on per-batch errors so the pipeline never halts.
"""

import os
import time

import httpx
import numpy as np
from dotenv import load_dotenv
from typing import List

from rich.progress import track

load_dotenv()

EMBED_MODEL = "nomic-embed-text"
BATCH_SIZE  = 8
VECTOR_DIM  = 768
MAX_RETRIES = 3
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
_EMBED_URL  = f"{OLLAMA_HOST.rstrip('/')}/api/embed"


def _embed_batch(batch: List[str]) -> List[np.ndarray]:
    """Call Ollama /api/embed in batch mode (single POST, list input)."""
    resp = httpx.post(
        _EMBED_URL,
        json={"model": EMBED_MODEL, "input": batch},
        timeout=120.0,
    )
    resp.raise_for_status()
    return [np.array(e, dtype=np.float32) for e in resp.json()["embeddings"]]


def embed_texts(texts: List[str]) -> List[np.ndarray]:
    """
    Returns a list of 768-dimensional float32 numpy arrays,
    one per input text, in the same order.
    """
    batches = [texts[i: i + BATCH_SIZE] for i in range(0, len(texts), BATCH_SIZE)]
    all_embeddings: List[np.ndarray] = []
    for batch in track(batches, description="Embedding chunks..."):
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                all_embeddings.extend(_embed_batch(batch))
                break
            except Exception as exc:
                if attempt == MAX_RETRIES:
                    print(f"[WARN] Embedding batch failed after {MAX_RETRIES} attempts: {exc}. Inserting zero vectors.")
                    all_embeddings.extend(
                        [np.zeros(VECTOR_DIM, dtype=np.float32)] * len(batch)
                    )
                else:
                    time.sleep(2 ** attempt)
    return all_embeddings


def embed_single(text: str) -> np.ndarray:
    """Convenience wrapper used at query time."""
    return embed_texts([text])[0]
