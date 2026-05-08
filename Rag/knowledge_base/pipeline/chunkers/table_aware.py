"""
Table-aware chunking.
Rule: ONE markdown table = ONE chunk, never split across boundaries.
Always prepend page title + section heading + caption for full context.
Non-table prose falls back to fixed_overlap chunking.

Use for: KDIGO GFR/Albuminuria tables, CBC ranges, ADA HbA1c targets,
         lab_* reference files, CKD staging.
"""

import re
from typing import List

from .hierarchical import Chunk
from .fixed_overlap import chunk_fixed_overlap


# Matches: optional caption (non-table line), optional blank line, header, separator, data rows
TABLE_PATTERN = re.compile(
    r"((?:^(?!\|).+\n)?)"      # optional caption (non-| line)
    r"\n?"                       # optional blank line between caption and header
    r"(\|.+\|\n"               # header row
    r"(?:\|[-:| ]+\|\n)"       # separator row
    r"(?:\|.+\|\n?)+)",        # one or more data rows
    re.MULTILINE,
)


def chunk_table_aware(
    markdown_text: str,
    page_title: str = "",
    section_heading: str = "",
) -> List[Chunk]:
    """
    Extracts tables as standalone chunks.
    Remaining prose is chunked with fixed_overlap.
    """
    chunks: List[Chunk] = []
    last_end = 0
    prose_parts: List[str] = []

    for match in TABLE_PATTERN.finditer(markdown_text):
        # Collect prose that precedes this table
        prose_before = markdown_text[last_end: match.start()].strip()
        if prose_before:
            prose_parts.append(prose_before)

        caption  = match.group(1).strip()
        table_md = match.group(2).strip()

        # Build context prefix
        prefix_parts = [p for p in [page_title, section_heading, caption] if p]
        prefix  = " | ".join(prefix_parts)
        content = f"{prefix}\n\n{table_md}" if prefix else table_md

        chunks.append(Chunk(content=content, chunk_type="table", parent_id=None))
        last_end = match.end()

    # Remaining prose after the last table
    remaining = markdown_text[last_end:].strip()
    if remaining:
        prose_parts.append(remaining)

    # Chunk all prose sections with fixed_overlap
    for prose in prose_parts:
        chunks.extend(chunk_fixed_overlap(prose))

    # If no tables were found at all, fall back entirely to fixed_overlap
    if not chunks:
        chunks = chunk_fixed_overlap(markdown_text)

    return chunks
