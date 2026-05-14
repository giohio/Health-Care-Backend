"""
Entry point for the HealthAI knowledge base ingestion pipeline.

Reads .md files from rag_knowledge_base/, chunks them with the appropriate
strategy, embeds with nomic-embed-text (Ollama), deduplicates, then upserts
into Qdrant.

Two collections:
  - clinical_guidelines : files under rag_knowledge_base/clinical/
  - patient_education   : files under rag_knowledge_base/patient/

Usage:
    cd "AI Service/knowledge_base"
    python run_pipeline.py                     # both collections
    python run_pipeline.py --collection clinical
    python run_pipeline.py --collection patient

Prerequisites:
    docker-compose up -d          (Qdrant at :6333, Ollama at :11434)
    docker exec -it ollama ollama pull nomic-embed-text
"""

import re
import sys
import argparse
from pathlib import Path
from typing import List, Tuple

import numpy as np
from rich.console import Console


# Resolve paths so the script works regardless of cwd
_HERE     = Path(__file__).parent.resolve()
# New KB at d:/microservice/rag_knowledge_base/ (v2 structure)
_RAW_DIR  = _HERE.parent.parent / "rag_knowledge_base"

# Sub-directories mapping to Qdrant collections
COLLECTION_MAP = {
    "clinical": (_RAW_DIR / "clinical",  "clinical_guidelines"),
    "patient":  (_RAW_DIR / "patient",   "patient_education"),
}

# Make pipeline/retriever importable
sys.path.insert(0, str(_HERE))

from pipeline.classifier import classify_file
from pipeline.chunkers.hierarchical import chunk_hierarchical
from pipeline.chunkers.semantic import chunk_semantic
from pipeline.chunkers.fixed_overlap import chunk_fixed_overlap
from pipeline.chunkers.table_aware import chunk_table_aware
from pipeline.metadata import build_payload
from pipeline.embedder import embed_texts
from pipeline.deduplicator import deduplicate
from pipeline.qdrant_loader import get_client, ensure_collection, upsert_chunks

console = Console()

# Minimum content length (chars) — skip near-empty files
MIN_FILE_CHARS = 200


def _is_page_not_found(text: str) -> bool:
    """Guard against any remaining scraped 404 pages."""
    indicators = [
        "# Page not found",
        "# **Page not found**",
        "Warning: Target URL returned error 404",
        "Page not found • Life in the Fast Lane",
    ]
    preview = text[:3000]
    return any(ind in preview for ind in indicators)


def process_file(
    filepath: Path,
    collection_name: str = "clinical_guidelines",
) -> List[Tuple[str, np.ndarray, dict]]:
    """
    Process one markdown file.
    Returns list of (chunk_id_hex, vector, payload_dict).
    """
    text = filepath.read_text(encoding="utf-8", errors="replace")

    # Safety: skip any lingering 404 pages
    if _is_page_not_found(text):
        console.print(f"[yellow]SKIP[/yellow] (page-not-found): {filepath.name}")
        return []

    if len(text.strip()) < MIN_FILE_CHARS:
        console.print(f"[yellow]SKIP[/yellow] (too short): {filepath.name}")
        return []

    config     = classify_file(filepath)
    strategy   = config["strategy"]
    department = config["department"]
    source     = config["source_type"].value

    # ── Chunking ────────────────────────────────────────────────────────────
    if strategy == "hierarchical":
        raw_chunks = chunk_hierarchical(text)

    elif strategy == "semantic":
        def embed_fn(sentences: List[str]) -> List[np.ndarray]:
            return embed_texts(sentences)
        raw_chunks = chunk_semantic(text, embed_fn)

    elif strategy == "table_aware":
        _note_match = re.search(r"^note:\s*(.+)$", text[:500], re.MULTILINE)
        _page_title  = _note_match.group(1).strip() if _note_match else ""
        raw_chunks = chunk_table_aware(text, page_title=_page_title)

    else:    # fixed_overlap
        raw_chunks = chunk_fixed_overlap(text)

    if not raw_chunks:
        return []

    # ── Build payloads ──────────────────────────────────────────────────────
    payloads_built: List[Tuple[str, object]] = []
    for chunk in raw_chunks:
        payload = build_payload(
            chunk_text    = chunk.content,
            chunk_type    = chunk.chunk_type,
            parent_id     = chunk.parent_id,
            source_type   = source,
            department    = department,
            filepath      = filepath,
            markdown_text = text,
            collection    = collection_name,
        )
        payloads_built.append((chunk.chunk_id, payload))

    # ── Embed all texts in one batch call ───────────────────────────────────
    texts_only = [p.text for _, p in payloads_built]
    vectors    = embed_texts(texts_only)

    # ── Assemble final tuples ───────────────────────────────────────────────
    assembled = [
        (cid, vec, pay.to_dict())
        for (cid, pay), vec in zip(payloads_built, vectors)
    ]

    return assembled


def main() -> None:
    parser = argparse.ArgumentParser(description="HealthAI KB ingestion pipeline")
    parser.add_argument(
        "--collection", choices=["clinical", "patient", "all"], default="all",
        help="Which collection to rebuild (default: all)"
    )
    args = parser.parse_args()

    console.print("[bold green]HealthAI Knowledge Base Builder[/bold green]")

    if not _RAW_DIR.exists():
        console.print(
            f"[red]ERROR[/red]: KB directory not found at {_RAW_DIR}"
        )
        sys.exit(1)

    targets = (
        [args.collection] if args.collection != "all"
        else list(COLLECTION_MAP.keys())
    )

    client = get_client()

    for col_key in targets:
        source_dir, collection_name = COLLECTION_MAP[col_key]
        console.print(f"\n[bold cyan]Collection: {collection_name}[/bold cyan]")
        console.print(f"Reading from: [cyan]{source_dir}[/cyan]")

        if not source_dir.exists():
            console.print(f"[yellow]SKIP[/yellow]: {source_dir} not found")
            continue

        # Ensure collection exists
        ensure_collection(client, collection_name)

        # Discover markdown files
        md_files = sorted(source_dir.rglob("*.md"))
        console.print(f"Found [bold]{len(md_files)}[/bold] markdown files")

        # Chunk + embed
        all_chunks: List[Tuple] = []
        total_files = len(md_files)
        for idx, filepath in enumerate(md_files, 1):
            console.print(f"[{idx}/{total_files}] {filepath.name}", end=" ")
            try:
                chunks = process_file(filepath, collection_name=collection_name)
                all_chunks.extend(chunks)
                console.print(f"-> {len(chunks)} chunks")
            except Exception as exc:
                console.print(f"[red]ERROR[/red]: {exc}")

        console.print(f"Total chunks before dedup: [bold]{len(all_chunks)}[/bold]")

        # Deduplicate
        unique_chunks = deduplicate(all_chunks)
        console.print(f"Unique chunks to upsert: [bold]{len(unique_chunks)}[/bold]")

        # Upsert to Qdrant
        upsert_chunks(client, unique_chunks, collection_name)

        console.print(f"[bold green]{collection_name} complete.[/bold green]")

    console.print("\n[bold green]Pipeline complete.[/bold green]")
    console.print(
        "Next: run [cyan]python eval/eval_retrieval.py[/cyan] to verify quality."
    )


if __name__ == "__main__":
    main()
