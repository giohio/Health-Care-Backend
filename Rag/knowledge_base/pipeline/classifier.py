"""
Rule-based classifier — maps a markdown file to its source type.
Reads YAML frontmatter (source_url, department) instead of directory name,
because the existing rag_knowledge_base/ is organised by department, not source.
"""

import re
from pathlib import Path
from enum import Enum
from typing import Optional


class SourceType(str, Enum):
    RADIOPAEDIA   = "radiopaedia"
    STATPEARLS    = "statpearls"
    DERMNET       = "dermnet"
    AAO           = "aao"
    KDIGO         = "kdigo"
    LITFL         = "litfl"
    MERCK_ATS_ADA = "merck_ats_ada"
    LAB_REFERENCE = "lab_reference"   # labtestsonline + explicit lab_* slugs


# Maps source type → chunking strategy
SOURCE_STRATEGY: dict[SourceType, str] = {
    SourceType.RADIOPAEDIA:   "hierarchical",
    SourceType.STATPEARLS:    "hierarchical",
    SourceType.DERMNET:       "semantic",
    SourceType.AAO:           "semantic",
    SourceType.KDIGO:         "table_aware",
    SourceType.LITFL:         "fixed_overlap",
    SourceType.MERCK_ATS_ADA: "fixed_overlap",
    SourceType.LAB_REFERENCE: "table_aware",
}

# source_url domain substring → SourceType
DOMAIN_MAP: list[tuple[str, SourceType]] = [
    ("radiopaedia.org",       SourceType.RADIOPAEDIA),
    ("ncbi.nlm.nih.gov",      SourceType.STATPEARLS),
    ("dermnetnz.org",         SourceType.DERMNET),
    ("eyewiki.aao.org",       SourceType.AAO),
    ("kdigo.org",             SourceType.KDIGO),
    ("litfl.com",             SourceType.LITFL),
    ("ecgpedia.org",          SourceType.LITFL),      # ECG Pedia → dense prose like LITFL
    ("merckmanuals.com",      SourceType.MERCK_ATS_ADA),
    ("labtestsonline.org.uk", SourceType.LAB_REFERENCE),
]

# Composite department → normalised form
DEPT_NORMALIZE: dict[str, Optional[str]] = {
    "hematology_internal":      "hematology",
    "nephrology_endocrinology": None,    # resolved from slug keywords below
}

# Keywords to split nephrology_endocrinology into its two sub-departments
_NEPHRO_KW = {"ckd", "kidney", "egfr", "creatinine", "dialysis", "albumin",
               "bun", "renal", "urea", "gfr"}
_ENDO_KW   = {"diabetes", "hba1c", "glucose", "insulin", "glycemic",
               "metformin", "type2", "type_2"}


# ── Internal helpers ────────────────────────────────────────────────────────

def _parse_frontmatter(filepath: Path) -> dict:
    """
    Parse YAML-like frontmatter (--- ... ---) using simple key:value regex.
    Avoids pyyaml dependency; handles the limited frontmatter format used here.
    """
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    if not content.startswith("---"):
        return {}
    end = content.find("\n---", 3)
    if end == -1:
        return {}
    fm_block = content[3:end]
    result: dict = {}
    for line in fm_block.splitlines():
        m = re.match(r"^(\w+):\s*(.+)$", line.strip())
        if m:
            result[m.group(1)] = m.group(2).strip()
    return result


def _url_to_source_type(url: str) -> Optional[SourceType]:
    for domain, st in DOMAIN_MAP:
        if domain in url:
            return st
    return None


def _normalize_department(dept_raw: str, slug: str) -> str:
    """
    Map composite or non-standard department names to canonical form.
    """
    if dept_raw not in DEPT_NORMALIZE:
        return dept_raw or "internal_medicine"

    canonical = DEPT_NORMALIZE[dept_raw]
    if canonical is not None:
        return canonical

    # nephrology_endocrinology — infer from slug keywords
    slug_lower = slug.lower()
    tokens = set(re.split(r"[\W_]+", slug_lower))
    if tokens & _NEPHRO_KW:
        return "nephrology"
    if tokens & _ENDO_KW:
        return "endocrinology"
    return "nephrology"     # default for the combined folder


# ── Public API ──────────────────────────────────────────────────────────────

def classify_file(filepath: Path) -> dict:
    """
    Returns {
        "source_type": SourceType,
        "strategy":    str,
        "department":  str,
    }

    Resolution order:
    1. Read YAML frontmatter for source_url → determine source type.
    2. Override to LAB_REFERENCE if slug starts with "lab_", or contains
       "interpretation" / "staging" (these always need table_aware chunking).
    3. Fall back to directory-name pattern if frontmatter is missing.
    """
    fm         = _parse_frontmatter(filepath)
    source_url = fm.get("source_url", "")
    dept_raw   = fm.get("department", "")
    slug       = fm.get("slug", filepath.stem)

    # Step 1 — source type from URL domain
    source_type = _url_to_source_type(source_url)

    # Step 2 — override for lab / table-heavy slugs
    slug_lower = slug.lower()
    if (slug_lower.startswith("lab_")
            or "interpretation" in slug_lower
            or "staging" in slug_lower):
        source_type = SourceType.LAB_REFERENCE

    # Step 3 — fallback: scan directory name
    if source_type is None:
        parent = filepath.parent.name.lower()
        for st in SourceType:
            if st.value in parent:
                source_type = st
                break
        if source_type is None:
            source_type = SourceType.STATPEARLS   # safest default (hierarchical)

    department = _normalize_department(dept_raw, slug)

    return {
        "source_type": source_type,
        "strategy":    SOURCE_STRATEGY[source_type],
        "department":  department,
    }
