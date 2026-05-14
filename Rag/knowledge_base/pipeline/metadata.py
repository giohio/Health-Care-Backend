"""
Metadata builder.
Every chunk that goes into Qdrant MUST carry this full payload —
missing a field breaks filter queries at retrieval time.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# Canonical department list — matches Qdrant payload filter values
VALID_DEPARTMENTS = {
    "respiratory", "dermatology", "neurology", "ophthalmology",
    "cardiology", "nephrology", "hematology", "endocrinology",
    "internal_medicine", "radiology",
}


@dataclass
class ChunkPayload:
    # ── Routing / filter fields ─────────────────────────────────────────────
    department:        str      # MUST be in VALID_DEPARTMENTS
    disease_category:  str      # e.g. "pneumonia", "melanoma", "ckd_stage3"
    source:            str      # "radiopaedia" | "statpearls" | "dermnet" | …
    chunk_type:        str      # "parent" | "child" | "sentence_group" | "fixed" | "table"
    document_type:     str      # "guideline" | "article" | "patient_info"
    collection:        str      # Qdrant collection name

    # ── Traceability ────────────────────────────────────────────────────────
    parent_id:         Optional[str]
    page_title:        str
    section_heading:   str
    source_url:        str      # original URL or file:// path

    # ── Content ─────────────────────────────────────────────────────────────
    text:              str      # actual chunk text (also stored as vector)

    # ── Quality ─────────────────────────────────────────────────────────────
    char_count:        int
    token_estimate:    int      # char_count // 4

    def to_dict(self) -> dict:
        return {
            "department":       self.department,
            "disease_category": self.disease_category,
            "source":           self.source,
            "chunk_type":       self.chunk_type,
            "document_type":    self.document_type,
            "collection":       self.collection,
            "parent_id":        self.parent_id,
            "page_title":       self.page_title,
            "section_heading":  self.section_heading,
            "source_url":       self.source_url,
            "text":             self.text,
            "char_count":       self.char_count,
            "token_estimate":   self.token_estimate,
        }


# ── Disease category inference ──────────────────────────────────────────────

_DISEASE_MAP: list[tuple[str, list[str]]] = [
    ("pneumonia",            ["pneumonia", "consolidation", "lobar"]),
    ("copd",                 ["copd", "chronic obstructive", "emphysema"]),
    ("asthma",               ["asthma", "bronchospasm", "spirometry"]),
    ("bronchitis",           ["bronchitis", "acute bronchitis"]),
    ("melanoma",             ["melanoma", "malignant melanoma", "abcde"]),
    ("basal_cell",           ["basal cell carcinoma", "bcc", "pearly"]),
    ("actinic_keratosis",    ["actinic keratosis", "ak ", "sun damage"]),
    ("seborrhoeic_keratosis",["seborrhoeic keratosis", "bkl", "stuck-on"]),
    ("dermatofibroma",       ["dermatofibroma", "df "]),
    ("melanocytic_naevus",   ["melanocytic naevus", "naevus", "benign mole"]),
    ("ckd",                  ["ckd", "chronic kidney disease", "gfr stage",
                               "egfr", "staging"]),
    ("diabetic_retinopathy", ["diabetic retinopathy", "fundus", "aptos"]),
    ("diabetic_macular_edema",["macular edema", "dme", "oct findings"]),
    ("ecg_arrhythmia",       ["arrhythmia", "afib", "atrial fibril",
                               "tachycardia", "bradycardia", "lbbb", "qrs"]),
    ("brain_tumor",          ["glioma", "meningioma", "glioblastoma",
                               "astrocytoma", "pituitary adenoma"]),
    ("cbc_interpretation",   ["cbc", "complete blood count", "hemoglobin",
                               "wbc", "platelet"]),
    ("iron_deficiency_anemia",["iron deficiency", "microcytic", "mcv"]),
    ("leukemia",             ["leukemia", "leukocyte", "blast"]),
    ("diabetes",             ["hba1c", "type 2 diabetes", "glycemic",
                               "metformin", "insulin resistance"]),
    ("hypertension",         ["hypertension", "blood pressure"]),
    ("pulmonary_opacity",    ["opacity", "ground-glass", "atelectasis"]),
    ("bone_fracture",        ["bone fracture", "fracture line", "dislocation",
                               "avulsion", "salter-harris", "AO classification"]),
    ("degenerative_spine",   ["spondylosis", "disc degeneration", "osteophyte spine",
                               "spondylolisthesis", "disc space narrowing"]),
    ("bowel_obstruction",    ["bowel gas pattern", "dilated bowel", "obstruction",
                               "small bowel obstruction", "large bowel obstruction"]),
]


def infer_disease_category(text: str, page_title: str) -> str:
    combined = (page_title + " " + text[:600]).lower()
    for category, keywords in _DISEASE_MAP:
        if any(kw in combined for kw in keywords):
            return category
    return "general"


# ── Page-level metadata extraction ─────────────────────────────────────────

def _extract_frontmatter_value(content: str, key: str) -> str:
    """Pull a single key from YAML frontmatter."""
    m = re.search(rf"^{key}:\s*(.+)$", content[:1000], re.MULTILINE)
    return m.group(1).strip() if m else ""


def extract_page_metadata(markdown_text: str, filepath: Path) -> dict:
    """Return page_title, section_heading, and source_url from the file."""
    # Prefer values from frontmatter when available
    source_url = _extract_frontmatter_value(markdown_text, "source_url")

    page_title = ""
    section_heading = ""

    # Look in body text (skip frontmatter block)
    body_start = 0
    if markdown_text.startswith("---"):
        end_fm = markdown_text.find("\n---", 3)
        body_start = end_fm + 4 if end_fm != -1 else 0

    for line in markdown_text[body_start:].split("\n")[:40]:
        if line.startswith("# ") and not page_title:
            page_title = line.lstrip("# ").strip()
        if line.startswith("## ") and not section_heading:
            section_heading = line.lstrip("# ").strip()

    if not page_title:
        # Fallback: prettify filename
        page_title = (
            filepath.stem.replace("_", " ").replace("-", " ").title()
        )

    return {
        "page_title":      page_title,
        "section_heading": section_heading,
        "source_url":      source_url or f"file://{filepath.resolve()}",
    }


def infer_document_type(source_type: str, collection: str, filepath: Path) -> str:
    """Map source/collection metadata to the report-level document_type tag."""
    if collection == "patient_education":
        return "patient_info"

    slug = filepath.stem.lower()
    if slug.startswith("lab_") or source_type in {"kdigo", "litfl", "merck_ats_ada", "lab_reference"}:
        return "guideline"

    return "article"


# ── Main builder ────────────────────────────────────────────────────────────

def build_payload(
    chunk_text:    str,
    chunk_type:    str,
    parent_id:     Optional[str],
    source_type:   str,
    department:    str,
    filepath:      Path,
    markdown_text: str,
    collection:    str = "clinical_guidelines",
) -> ChunkPayload:
    meta        = extract_page_metadata(markdown_text, filepath)
    disease_cat = infer_disease_category(chunk_text, meta["page_title"])
    doc_type    = infer_document_type(source_type, collection, filepath)

    # Ensure department is in the valid set; fall back to internal_medicine
    dept = department if department in VALID_DEPARTMENTS else "internal_medicine"

    return ChunkPayload(
        department       = dept,
        disease_category = disease_cat,
        source           = source_type,
        chunk_type       = chunk_type,
        document_type    = doc_type,
        collection       = collection,
        parent_id        = parent_id,
        page_title       = meta["page_title"],
        section_heading  = meta["section_heading"],
        source_url       = meta["source_url"],
        text             = chunk_text,
        char_count       = len(chunk_text),
        token_estimate   = len(chunk_text) // 4,
    )
