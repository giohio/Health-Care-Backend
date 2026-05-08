"""
Fixed-size chunking with ~20 % overlap.
Best for sources with sparse headings and dense prose.

Use for: LITFL ECG Library, ECGPedia, ATS/AHA guidelines, Merck Manuals.
"""

from typing import List

from langchain_text_splitters import RecursiveCharacterTextSplitter

from .hierarchical import Chunk

CHUNK_SIZE = 512
OVERLAP    = 102    # ≈ 20 % of 512


def chunk_fixed_overlap(markdown_text: str) -> List[Chunk]:
    """Returns Chunk objects with chunk_type='fixed' and no parent/child links."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=OVERLAP,
        separators=["\n\n", "\n", ". ", " "],
        keep_separator=True,
    )

    texts = splitter.split_text(markdown_text)

    return [
        Chunk(content=t.strip(), chunk_type="fixed", parent_id=None)
        for t in texts
        if len(t.strip()) > 50
    ]
