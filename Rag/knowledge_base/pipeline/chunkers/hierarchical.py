"""
Hierarchical chunking: splits at H2 headings to create parent chunks (≤1024 tokens),
then further splits each parent into child chunks (≤256 tokens).
Each child stores a reference to its parent's ID.

Use for: Radiopaedia (structured H1/H2/H3 articles), StatPearls (section-heavy).
"""

import re
import hashlib
from dataclasses import dataclass, field
from typing import List, Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter


@dataclass
class Chunk:
    content:    str
    chunk_type: str                # "parent" | "child" | "table" | "sentence_group" | "fixed"
    parent_id:  Optional[str]
    chunk_id:   str = field(init=False)

    def __post_init__(self) -> None:
        self.chunk_id = hashlib.sha256(
            self.content.encode("utf-8")
        ).hexdigest()[:16]


PARENT_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=1024,
    chunk_overlap=0,
    separators=["\n## ", "\n### ", "\n\n", "\n", " "],
)

CHILD_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=256,
    chunk_overlap=30,
    separators=["\n\n", "\n", ". ", " "],
)


def chunk_hierarchical(markdown_text: str) -> List[Chunk]:
    """
    Returns a flat list of Chunk objects (parents + their children interleaved).
    """
    chunks: List[Chunk] = []

    # Split at H2 headings to get logical sections
    sections = re.split(r"(?=\n## )", markdown_text)

    for section in sections:
        if len(section.strip()) < 50:       # skip stub sections
            continue

        parent_texts = PARENT_SPLITTER.split_text(section)

        for parent_text in parent_texts:
            parent = Chunk(
                content=parent_text.strip(),
                chunk_type="parent",
                parent_id=None,
            )
            chunks.append(parent)

            child_texts = CHILD_SPLITTER.split_text(parent_text)
            for child_text in child_texts:
                if len(child_text.strip()) < 40:    # skip trivial fragments
                    continue
                child = Chunk(
                    content=child_text.strip(),
                    chunk_type="child",
                    parent_id=parent.chunk_id,
                )
                chunks.append(child)

    return chunks
