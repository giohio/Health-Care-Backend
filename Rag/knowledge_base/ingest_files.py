"""
One-shot targeted ingest: add specific files into an existing Qdrant collection.

Usage:
    python ingest_files.py <file1.md> [file2.md ...]

Example:
    python ingest_files.py \
        ../../Rag/rag_knowledge_base/respiratory/disease_sarcoidosis_hilar.md \
        ../../Rag/rag_knowledge_base/dermatology/dermoscopy_melanoma_criteria.md
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.resolve()))

from run_pipeline import process_file
from pipeline.deduplicator import deduplicate
from pipeline.qdrant_loader import get_client, upsert_chunks, COLLECTION_NAME
from rich.console import Console

console = Console()


def main() -> None:
    if len(sys.argv) < 2:
        console.print("[red]Usage:[/red] python ingest_files.py <file1.md> [file2.md ...]")
        sys.exit(1)

    files = [Path(p).resolve() for p in sys.argv[1:]]
    missing = [f for f in files if not f.exists()]
    if missing:
        for m in missing:
            console.print(f"[red]Not found:[/red] {m}")
        sys.exit(1)

    client = get_client()
    all_chunks = []

    for filepath in files:
        console.print(f"Processing: [cyan]{filepath.name}[/cyan]", end=" ")
        try:
            chunks = process_file(filepath)
            all_chunks.extend(chunks)
            console.print(f"-> {len(chunks)} chunks")
        except Exception as exc:
            console.print(f"[red]ERROR[/red]: {exc}")

    unique = deduplicate(all_chunks)
    console.print(f"Unique chunks to upsert: [bold]{len(unique)}[/bold]")
    upsert_chunks(client, unique, COLLECTION_NAME)
    console.print(f"[bold green]Done — upserted into '{COLLECTION_NAME}'.[/bold green]")


if __name__ == "__main__":
    main()
