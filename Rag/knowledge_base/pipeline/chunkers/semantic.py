"""
Semantic sentence-level chunking.
Groups sentences by cosine similarity; when similarity drops below threshold
a new chunk begins. Max chunk size: 512 tokens (≈2048 chars).

Use for: DermNet NZ, AAO EyeWiki, KDIGO prose sections.
"""

import re
import hashlib
from typing import List, Callable

import numpy as np

from .hierarchical import Chunk

SIMILARITY_THRESHOLD = 0.82     # sentences below this cosine sim start a new chunk
MAX_CHUNK_TOKENS     = 512
AVG_CHARS_PER_TOKEN  = 4        # rough estimate without a tokeniser


def _sentence_split(text: str) -> List[str]:
    """Simple rule-based sentence splitter for English medical text."""
    text = re.sub(r"\n+", " ", text)
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
    return [s.strip() for s in sentences if len(s.strip()) > 20]


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom <= 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


def chunk_semantic(
    markdown_text: str,
    embed_fn: Callable[[List[str]], List[np.ndarray]],
) -> List[Chunk]:
    """
    embed_fn: callable(List[str]) -> List[np.ndarray]
    Batches all sentence embeddings at once for efficiency.
    """
    sentences = _sentence_split(markdown_text)
    if not sentences:
        return []

    embeddings = embed_fn(sentences)

    groups: List[List[str]] = []
    current_group: List[str] = [sentences[0]]
    current_tokens = len(sentences[0]) // AVG_CHARS_PER_TOKEN

    for i in range(1, len(sentences)):
        sim = _cosine_sim(embeddings[i - 1], embeddings[i])
        token_estimate = len(sentences[i]) // AVG_CHARS_PER_TOKEN

        if (sim >= SIMILARITY_THRESHOLD
                and (current_tokens + token_estimate) <= MAX_CHUNK_TOKENS):
            current_group.append(sentences[i])
            current_tokens += token_estimate
        else:
            groups.append(current_group)
            current_group = [sentences[i]]
            current_tokens = token_estimate

    groups.append(current_group)

    return [
        Chunk(
            content=" ".join(g).strip(),
            chunk_type="sentence_group",
            parent_id=None,
        )
        for g in groups
        if len(" ".join(g).strip()) > 60
    ]
