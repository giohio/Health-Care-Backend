"""
Creates the Qdrant collection (idempotent) and upserts chunks in batches.
Point IDs: sha256[:16] hex converted to unsigned int (Qdrant uint64 format).
Re-running the pipeline is safe — the deduplicator skips known content,
and Qdrant upsert overwrites matching IDs harmlessly.
"""

import os
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from typing import List, Tuple

from qdrant_client import QdrantClient

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    PayloadSchemaType,
)


COLLECTION_NAME = "clinical_guidelines"   # must match run_pipeline.py COLLECTION_MAP
VECTOR_DIM      = 768
QDRANT_URL      = os.getenv("QDRANT_URL", "http://localhost:6333")

# Payload fields to index — improves filter query performance
INDEXED_FIELDS: List[Tuple[str, PayloadSchemaType]] = [
    ("department",       PayloadSchemaType.KEYWORD),
    ("disease_category", PayloadSchemaType.KEYWORD),
    ("source",           PayloadSchemaType.KEYWORD),
    ("chunk_type",       PayloadSchemaType.KEYWORD),
]


def get_client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL)


def ensure_collection(client: QdrantClient, collection_name: str = COLLECTION_NAME) -> None:
    """
    Create collection and payload indexes if they do not exist.
    Safe to call multiple times — existing resources are not modified.
    """
    existing_names = [c.name for c in client.get_collections().collections]

    if collection_name not in existing_names:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=VECTOR_DIM,
                distance=Distance.COSINE,
            ),
        )
        print(f"[INFO] Created Qdrant collection: {collection_name}")
    else:
        print(f"[INFO] Collection '{collection_name}' already exists — skipping creation.")

    for field_name, field_type in INDEXED_FIELDS:
        try:
            client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=field_type,
            )
        except Exception:
            pass    # index already exists — safe to ignore


def _hex_to_point_id(chunk_id_hex: str) -> int:
    """
    Convert 16-char hex string to uint64 for use as Qdrant point ID.
    Qdrant accepts both UUID strings and unsigned integers.
    """
    return int(chunk_id_hex, 16)


def upsert_chunks(
    client:          QdrantClient,
    chunks:          List[Tuple[str, np.ndarray, dict]],
    collection_name: str = COLLECTION_NAME,
    batch_size:      int = 64,
) -> None:
    """
    chunks: list of (chunk_id_hex, vector_np_float32, payload_dict)
    """
    total = len(chunks)
    for i in range(0, total, batch_size):
        batch = chunks[i: i + batch_size]
        points = [
            PointStruct(
                id=_hex_to_point_id(chunk_id_hex),
                vector=vector.tolist(),
                payload=payload,
            )
            for chunk_id_hex, vector, payload in batch
        ]
        client.upsert(
            collection_name=collection_name,
            points=points,
            wait=True,
        )

    print(f"[INFO] Upserted {total} points into '{collection_name}'.")
