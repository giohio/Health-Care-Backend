"""
Standalone PDF generation test — no external service dependencies.
Run with: python tests/test_pdf_standalone.py
"""
import io
import sys
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# ── Minimal mock for what the endpoint would produce ─────────────────────────

RESULT_ID = "fa3bfbad-c838-41e3-8ffc-d135728b2f2e"
PATIENT_NAME = "Tran Thi B"
TEST_NAME = "Complete Blood Count (CBC) with Differential"
STATUS = "Published"
CREATED = "2025-03-10"

FINDINGS = [
    {"name": "White Blood Cell (WBC)", "value": 11.2, "unit": "×10⁹/L",
     "reference_low": 4.5, "reference_high": 11.0, "flag": "H"},
    {"name": "Red Blood Cell (RBC)", "value": 4.8, "unit": "×10¹²/L",
     "reference_low": 4.5, "reference_high": 5.5, "flag": "N"},
    {"name": "Hemoglobin (Hb)", "value": 13.5, "unit": "g/dL",
     "reference_low": 12.0, "reference_high": 17.0, "flag": "N"},
    {"name": "Platelet Count", "value": 180, "unit": "×10⁹/L",
     "reference_low": 150, "reference_high": 400, "flag": "N"},
    {"name": "Alanine Aminotransferase (ALT)", "value": 85, "unit": "U/L",
     "reference_low": 7, "reference_high": 56, "flag": "H"},
    {"name": "Blood Urea Nitrogen (BUN)", "value": 22, "unit": "mg/dL",
     "reference_low": 7, "reference_high": 20, "flag": "H"},
]

AI_SUMMARY = (
    "The CBC results show mild leukocytosis with neutrophilia, suggesting a possible "
    "mild bacterial infection. Liver enzymes are mildly elevated."
)

# ── Constants ────────────────────────────────────────────────────────────────

PAGE_W, _ = A4
L_MARGIN = R_MARGIN = 2 * cm
BODY_W = PAGE_W - L_MARGIN - R_MARGIN

CLR_NAVY   = colors.HexColor("#1a3a5c")
CLR_BLUE   = colors.HexColor("#2176ae")
CLR_LIGHT  = colors.HexColor("#eaf3fb")
CLR_HIGH   = colors.HexColor("#c0392b")
CLR_LOW    = colors.HexColor("#2980b9")
CLR_NORMAL = colors.HexColor("#27ae60")
CLR_BORDER = colors.HexColor("#c8d8e8")
CLR_MUTED  = colors.HexColor("#7f8c8d")
CLR_WHITE  = colors.HexColor("#ffffff")

# ── Helpers (copied from emr.py) ────────────────────────────────────────────

def para(text, **kw):
    d = dict(fontName="Helvetica", fontSize=9, leading=13, textColor=colors.black)
    d.update(kw)
    return Paragraph(str(text), ParagraphStyle("p", **d))

def bold(text, **kw):
    return para(text, fontName="Helvetica-Bold", **kw)

def section_bar(text, bg=CLR_NAVY):
    t = Table([[para(f"<b>{text}</b>", fontName="Helvetica-Bold", fontSize=10,
                      textColor=colors.white, leading=14)]], colWidths=[BODY_W])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
    ]))
    return t

def info_table(rows, col_widths=None):
    if col_widths is None:
        col_widths = [BODY_W * 0.33, BODY_W * 0.67]
    data = [[bold(lbl, fontSize=9), para(val, fontSize=9)] for lbl, val in rows]
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, -1), (-1, -1), 0.4, CLR_BORDER),
    ]))
    return t

def result_row(f, idx):
    name   = f.get("name") or f.get("finding", "N/A")
    value  = str(f.get("value", f.get("severity", "–")))
    unit   = f.get("unit", "")
    ref_l  = f.get("reference_low")
    ref_h  = f.get("reference_high")
    flag   = str(f.get("flag", "N")).upper()

    if ref_l is not None and ref_h is not None:
        ref_range = f"{ref_l} – {ref_h} {unit}".strip()
    else:
        ref_range = "–"

    value_str = f"{value} {unit}".strip() if unit else value

    if flag in ("H", "HIGH"):
        flag_label = "↑ High"
        flag_color = CLR_HIGH
    elif flag in ("L", "LOW"):
        flag_label = "↓ Low"
        flag_color = CLR_LOW
    elif flag in ("C", "CRITICAL"):
        flag_label = "⚠ Critical"
        flag_color = CLR_HIGH
    else:
        flag_label = "Normal"
        flag_color = CLR_NORMAL

    bg = CLR_WHITE if idx % 2 == 0 else CLR_LIGHT
    cells = [
        para(name, fontSize=9, leading=12),
        para(value_str, fontSize=9, leading=12, fontName="Helvetica-Bold"),
        para(ref_range, fontSize=9, leading=12),
        para(flag_label, fontSize=9, leading=12, fontName="Helvetica-Bold", textColor=flag_color),
    ]
    return cells, bg

# ── Build PDF ───────────────────────────────────────────────────────────────

buffer = io.BytesIO()
doc = SimpleDocTemplate(
    buffer,
    pagesize=A4,
    leftMargin=L_MARGIN,
    rightMargin=R_MARGIN,
    topMargin=1.5 * cm,
    bottomMargin=2 * cm,
)

story = []

# ① Hospital header
hdr_data = [[
    para("🏥  D-HEALTH HOSPITAL", fontName="Helvetica-Bold", fontSize=15,
          textColor=CLR_NAVY, leading=20),
    para("DEPARTMENT OF LABORATORY MEDICINE", fontName="Helvetica-Bold",
          fontSize=8.5, textColor=CLR_BLUE, leading=12, alignment=1),
]]
hdr = Table(hdr_data, colWidths=[BODY_W * 0.55, BODY_W * 0.45])
hdr.setStyle(TableStyle([
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("ALIGN", (1, 0), (1, 0), "RIGHT"),  # was 7 — now fixed
    ("LINEBELOW", (0, 0), (-1, -1), 2, CLR_NAVY),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
]))
story.append(hdr)
story.append(Spacer(1, 0.25 * cm))

# ② Title banner
banner = Table([[para("LABORATORY TEST REPORT", fontName="Helvetica-Bold", fontSize=13,
                       textColor=colors.white, leading=17, alignment=1)]],
                colWidths=[BODY_W])
banner.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), CLR_BLUE),
    ("TOPPADDING", (0, 0), (-1, -1), 9),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
]))
story.append(banner)
story.append(Spacer(1, 0.35 * cm))

# ③ Patient info
patient_rows = [
    ["Patient Name", PATIENT_NAME],
    ["Test Name", TEST_NAME],
    ["Specimen Date", CREATED],
    ["Report Status", STATUS],
    ["Report ID", RESULT_ID],
]
story.append(section_bar("PATIENT INFORMATION"))
story.append(Spacer(1, 0.15 * cm))
story.append(info_table(patient_rows))
story.append(Spacer(1, 0.4 * cm))

# ④ AI Summary
if AI_SUMMARY:
    story.append(section_bar("AI CLINICAL SUMMARY", bg=CLR_BLUE))
    story.append(Spacer(1, 0.15 * cm))
    summary_tbl = Table([[para(AI_SUMMARY, fontSize=9, leading=14,
                                textColor=colors.HexColor("#2c3e50"))]], colWidths=[BODY_W])
    summary_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CLR_LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, CLR_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(summary_tbl)
    story.append(Spacer(1, 0.4 * cm))

# ⑤ Detailed results
if FINDINGS:
    story.append(section_bar("DETAILED LABORATORY RESULTS", bg=CLR_NAVY))
    story.append(Spacer(1, 0.15 * cm))

    hdr_row = [
        bold("Test Parameter", fontSize=9, textColor=colors.white, leading=12),
        bold("Result", fontSize=9, textColor=colors.white, leading=12),
        bold("Reference Range", fontSize=9, textColor=colors.white, leading=12),
        bold("Flag", fontSize=9, textColor=colors.white, leading=12),
    ]
    table_data = [hdr_row]
    row_bgs = []
    for idx, f in enumerate(FINDINGS):
        cells, bg = result_row(f, idx)
        table_data.append(cells)
        row_bgs.append(bg)

    findings_tbl = Table(
        table_data,
        colWidths=[BODY_W * 0.36, BODY_W * 0.20, BODY_W * 0.26, BODY_W * 0.18],
        repeatRows=1,
    )
    ts = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), CLR_NAVY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.4, CLR_BORDER),
        ("LINEBELOW", (0, 0), (-1, 0), 1.5, CLR_BLUE),
    ])
    for idx, bg in enumerate(row_bgs, start=1):
        ts.add("BACKGROUND", (0, idx), (-1, idx), bg)
    findings_tbl.setStyle(ts)
    story.append(findings_tbl)
    story.append(Spacer(1, 0.4 * cm))

# ⑥ Disclaimer
disclaimer_lines = [
    "• This report is generated by an AI-assisted system and is intended for informational purposes only.",
    "• It does NOT constitute a medical diagnosis. Please consult your treating physician for clinical decisions.",
    "• Results should be interpreted in conjunction with clinical history and other diagnostic findings.",
]
disclaimer_tbl = Table([[para("<br/>".join(disclaimer_lines), fontSize=7.5, leading=11,
                                textColor=colors.HexColor("#7f8c8d"))]], colWidths=[BODY_W])
disclaimer_tbl.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fef9f9")),
    ("BOX", (0, 0), (-1, -1), 0.8, CLR_HIGH),
    ("TOPPADDING", (0, 0), (-1, -1), 8),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ("LEFTPADDING", (0, 0), (-1, -1), 10),
    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
]))
story.append(disclaimer_tbl)
story.append(Spacer(1, 0.25 * cm))

# ⑦ Signature
sig_data = [[
    para("Reviewed by: _______________________", fontSize=8, textColor=CLR_MUTED, leading=11),
    para("Authorised by: ______________________", fontSize=8, textColor=CLR_MUTED, leading=11, alignment=1),
]]
sig_tbl = Table(sig_data, colWidths=[BODY_W * 0.5, BODY_W * 0.5])
sig_tbl.setStyle(TableStyle([
    ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
    ("ALIGN", (1, 0), (1, 0), "RIGHT"),  # was 7 — now fixed
    ("LINEABOVE", (0, 0), (-1, 0), 0.5, CLR_BORDER),
    ("TOPPADDING", (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
]))
story.append(sig_tbl)

# ── Build & verify ──────────────────────────────────────────────────────────

doc.build(story)
buffer.seek(0)
content = buffer.getvalue()

assert content[:4] == b"%PDF", f"Expected PDF magic bytes, got {content[:4]!r}"
print(f"[PASS] PDF generated successfully: {len(content):,} bytes")
print(f"[PASS] Magic bytes correct: {content[:4]!r}")

# Write to file for manual inspection
out_path = "test_lab_report.pdf"
with open(out_path, "wb") as f:
    f.write(content)
print(f"[PASS] Written to {out_path} — open to inspect layout")
