"""
HealthAI Portal — Medical Knowledge Base Ingestion Pipeline v2
===============================================================
Mở rộng từ v1, bổ sung:
  - Collection CLINICAL: PDF guidelines (ESC, ADA, KDIGO, NICE, WHO) — cho bác sĩ
  - Collection PATIENT:  MedlinePlus API — cho bệnh nhân (plain language)
  - Jina Reader vẫn dùng cho web articles như v1

Cấu trúc output:
    rag_knowledge_base/
    ├── clinical/                  ← bác sĩ / UC2 / UC3
    │   ├── guidelines_pdf/        ← PDF lớn (ESC, ADA, KDIGO...)
    │   ├── respiratory/
    │   ├── dermatology/
    │   ├── neurology/
    │   ├── ophthalmology/
    │   ├── cardiology/
    │   ├── nephrology_endocrinology/
    │   └── hematology_internal/
    └── patient/                   ← bệnh nhân / UC1 / UC4
        └── medlineplus/           ← plain language từ NIH API

Usage:
    pip install requests python-dotenv
    python fetch_knowledge_base_v2.py

    # Chỉ fetch 1 collection:
    python fetch_knowledge_base_v2.py --collection clinical
    python fetch_knowledge_base_v2.py --collection patient

    # Chỉ fetch guidelines PDF:
    python fetch_knowledge_base_v2.py --collection clinical --mode pdfs

    # Chỉ fetch 1 department web articles:
    python fetch_knowledge_base_v2.py --collection clinical --dept cardiology

    # Dry run (không fetch thật):
    python fetch_knowledge_base_v2.py --dry-run
"""

import os
import time
import argparse
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OUTPUT_DIR        = "rag_knowledge_base"
CLINICAL_DIR      = os.path.join(OUTPUT_DIR, "clinical")
PATIENT_DIR       = os.path.join(OUTPUT_DIR, "patient")
PDF_DIR           = os.path.join(CLINICAL_DIR, "guidelines_pdf")
MEDLINEPLUS_DIR   = os.path.join(PATIENT_DIR, "medlineplus")

JINA_BASE         = "https://r.jina.ai/"
REQUEST_TIMEOUT   = 60
SLEEP_WEB         = 2.5   # giữa các web request (Jina)
SLEEP_PDF         = 3.0   # giữa các PDF download
SLEEP_API         = 1.0   # giữa các MedlinePlus API call
MAX_RETRIES       = 2

JINA_API_KEY = os.getenv("JINA_API_KEY")
if not JINA_API_KEY:
    raise EnvironmentError("JINA_API_KEY environment variable is not set.")

# ---------------------------------------------------------------------------
# COLLECTION 1: CLINICAL — Web articles (giống v1, giữ nguyên + mở rộng)
# ---------------------------------------------------------------------------

CLINICAL_WEB = {

    "respiratory": [
        {
            "url": "https://en.wikipedia.org/wiki/Pulmonology",
            "slug": "dept_overview_pulmonary", "chunk_type": "DEPARTMENT", "severity": "ROUTINE",
            "note": "Pulmonary department overview"
        },
        {
            "url": "https://en.wikipedia.org/wiki/Pneumonia",
            "slug": "disease_pneumonia_radiology", "chunk_type": "DISEASE", "severity": "URGENT",
            "note": "Pneumonia — clinical features, radiological findings, X-ray patterns"
        },
        {
            "url": "https://en.wikipedia.org/wiki/Lobar_pneumonia",
            "slug": "disease_lobar_pneumonia", "chunk_type": "DISEASE", "severity": "URGENT",
            "note": "Lobar pneumonia — consolidation patterns on CXR"
        },
        {
            "url": "https://en.wikipedia.org/wiki/Bronchopneumonia",
            "slug": "disease_bronchopneumonia", "chunk_type": "DISEASE", "severity": "URGENT",
            "note": "Bronchopneumonia — patchy opacities"
        },
        {
            "url": "https://en.wikipedia.org/wiki/Chest_X-ray",
            "slug": "normal_chest_xray_anatomy", "chunk_type": "GUIDELINE", "severity": "ROUTINE",
            "note": "Chest X-ray — anatomy, technique, interpretation"
        },
        {
            "url": "https://medlineplus.gov/ency/article/000145.htm",
            "slug": "statpearls_pneumonia", "chunk_type": "DISEASE", "severity": "URGENT",
            "note": "MedlinePlus Encyclopedia — Community-acquired pneumonia clinical overview"
        },
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK559109/",
            "slug": "statpearls_asthma", "chunk_type": "DISEASE", "severity": "URGENT",
            "note": "StatPearls — Asthma clinical features"
        },
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK482408/",
            "slug": "statpearls_copd", "chunk_type": "DISEASE", "severity": "URGENT",
            "note": "StatPearls — COPD diagnosis and GOLD classification"
        },
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK513273/",
            "slug": "statpearls_bronchitis", "chunk_type": "DISEASE", "severity": "ROUTINE",
            "note": "StatPearls — Acute vs chronic bronchitis"
        },
        {
            "url": "https://litfl.com/cxr-interpretation/",
            "slug": "cxr_systematic_approach", "chunk_type": "GUIDELINE", "severity": "ROUTINE",
            "note": "LITFL — Systematic CXR reading approach"
        },
        {
            "url": "https://en.wikipedia.org/wiki/Pulmonary_consolidation",
            "slug": "differential_pulmonary_opacity", "chunk_type": "GUIDELINE", "severity": "ROUTINE",
            "note": "Pulmonary opacity and consolidation differential"
        },
        # THÊM MỚI
        {
            "url": "https://www.nice.org.uk/guidance/ng138/chapter/Recommendations",
            "slug": "nice_pneumonia_guidelines", "chunk_type": "GUIDELINE", "severity": "URGENT",
            "note": "NICE NG138 — Pneumonia diagnosis and management (UK guideline)"
        },
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK560687/",
            "slug": "statpearls_curb65", "chunk_type": "GUIDELINE", "severity": "URGENT",
            "note": "StatPearls — CURB-65 pneumonia severity scoring"
        },
    ],

    "dermatology": [
        {
            "url": "https://dermnetnz.org/topics/dermoscopy",
            "slug": "dept_overview_dermoscopy", "chunk_type": "DEPARTMENT", "severity": "ROUTINE",
            "note": "Dermoscopy overview"
        },
        {
            "url": "https://dermnetnz.org/topics/melanoma",
            "slug": "disease_melanoma", "chunk_type": "DISEASE", "severity": "EMERGENCY",
            "note": "Melanoma — ABCDE criteria"
        },
        {
            "url": "https://dermnetnz.org/topics/melanocytic-naevus",
            "slug": "disease_melanocytic_naevus", "chunk_type": "DISEASE", "severity": "ROUTINE",
            "note": "Benign melanocytic naevus"
        },
        {
            "url": "https://dermnetnz.org/topics/basal-cell-carcinoma",
            "slug": "disease_bcc", "chunk_type": "DISEASE", "severity": "URGENT",
            "note": "Basal cell carcinoma (BCC)"
        },
        {
            "url": "https://dermnetnz.org/topics/actinic-keratosis",
            "slug": "disease_actinic_keratosis", "chunk_type": "DISEASE", "severity": "URGENT",
            "note": "Actinic keratosis (AK)"
        },
        {
            "url": "https://dermnetnz.org/topics/seborrhoeic-keratosis",
            "slug": "disease_seborrhoeic_keratosis", "chunk_type": "DISEASE", "severity": "ROUTINE",
            "note": "Seborrhoeic keratosis (BKL)"
        },
        {
            "url": "https://dermnetnz.org/topics/dermatofibroma",
            "slug": "disease_dermatofibroma", "chunk_type": "DISEASE", "severity": "ROUTINE",
            "note": "Dermatofibroma (DF)"
        },
        {
            "url": "https://dermnetnz.org/topics/vascular-lesions-of-the-skin",
            "slug": "disease_vascular_lesion", "chunk_type": "DISEASE", "severity": "ROUTINE",
            "note": "Vascular lesions (VASC)"
        },
        {
            "url": "https://dermnetnz.org/topics/how-to-diagnose-skin-lesions",
            "slug": "differential_skin_lesion_diagnosis", "chunk_type": "GUIDELINE", "severity": "ROUTINE",
            "note": "Skin lesion differential diagnosis"
        },
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK470538/",
            "slug": "statpearls_melanoma", "chunk_type": "DISEASE", "severity": "EMERGENCY",
            "note": "StatPearls — Melanoma staging"
        },
    ],

    "neurology": [
        {
            "url": "https://en.wikipedia.org/wiki/Magnetic_resonance_imaging_of_the_brain",
            "slug": "dept_overview_brain_mri", "chunk_type": "DEPARTMENT", "severity": "ROUTINE",
            "note": "Brain MRI systematic reading — approach and anatomy"
        },
        {
            "url": "https://en.wikipedia.org/wiki/Glioma",
            "slug": "disease_glioma", "chunk_type": "DISEASE", "severity": "EMERGENCY",
            "note": "Glioma — classification, MRI characteristics, WHO grading"
        },
        {
            "url": "https://en.wikipedia.org/wiki/Glioblastoma",
            "slug": "disease_glioblastoma", "chunk_type": "DISEASE", "severity": "EMERGENCY",
            "note": "Glioblastoma — ring enhancement, Stupp protocol, prognosis"
        },
        {
            "url": "https://en.wikipedia.org/wiki/Meningioma",
            "slug": "disease_meningioma", "chunk_type": "DISEASE", "severity": "URGENT",
            "note": "Meningioma — dural tail, extra-axial mass, WHO grading"
        },
        {
            "url": "https://en.wikipedia.org/wiki/Pituitary_adenoma",
            "slug": "disease_pituitary_adenoma", "chunk_type": "DISEASE", "severity": "URGENT",
            "note": "Pituitary adenoma — sellar mass, classification, treatment"
        },
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK441861/",
            "slug": "statpearls_brain_tumor", "chunk_type": "DISEASE", "severity": "EMERGENCY",
            "note": "StatPearls — Brain tumor classification"
        },
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK470578/",
            "slug": "statpearls_meningioma", "chunk_type": "DISEASE", "severity": "URGENT",
            "note": "StatPearls — Meningioma WHO grading"
        },
    ],

    "ophthalmology": [
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK560805/",
            "slug": "dept_overview_diabetic_retinopathy", "chunk_type": "DEPARTMENT", "severity": "ROUTINE",
            "note": "Diabetic retinopathy overview"
        },
        {
            "url": "https://en.wikipedia.org/wiki/Diabetic_retinopathy",
            "slug": "disease_proliferative_dr", "chunk_type": "DISEASE", "severity": "EMERGENCY",
            "note": "Proliferative diabetic retinopathy — neovascularization, staging"
        },
        {
            "url": "https://eyewiki.aao.org/Diabetic_Retinopathy",
            "slug": "aao_eyewiki_dr_classification", "chunk_type": "GUIDELINE", "severity": "ROUTINE",
            "note": "AAO EyeWiki — DR grading scale"
        },
        {
            "url": "https://en.wikipedia.org/wiki/Fundus_photography",
            "slug": "fundus_photography_reading", "chunk_type": "GUIDELINE", "severity": "ROUTINE",
            "note": "Fundus photograph interpretation — technique and findings"
        },
    ],

    "cardiology": [
        {
            "url": "https://litfl.com/ecg-library/basics/",
            "slug": "dept_overview_ecg_basics", "chunk_type": "DEPARTMENT", "severity": "ROUTINE",
            "note": "ECG basics — systematic reading"
        },
        {
            "url": "https://litfl.com/atrial-fibrillation-ecg-library/",
            "slug": "disease_atrial_fibrillation", "chunk_type": "DISEASE", "severity": "URGENT",
            "note": "Atrial fibrillation — irregularly irregular"
        },
        {
            "url": "https://litfl.com/ventricular-tachycardia-monomorphic-ecg-library/",
            "slug": "disease_ventricular_tachycardia", "chunk_type": "DISEASE", "severity": "EMERGENCY",
            "note": "Ventricular tachycardia — wide complex"
        },
        {
            "url": "https://litfl.com/premature-ventricular-complex-pvc-ecg-library/",
            "slug": "disease_pvc", "chunk_type": "DISEASE", "severity": "URGENT",
            "note": "PVC — wide bizarre QRS"
        },
        {
            "url": "https://litfl.com/st-elevation-ecg-library/",
            "slug": "differential_st_elevation", "chunk_type": "GUIDELINE", "severity": "EMERGENCY",
            "note": "ST elevation differential — STEMI vs benign"
        },
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK532939/",
            "slug": "statpearls_arrhythmia_overview", "chunk_type": "DISEASE", "severity": "URGENT",
            "note": "StatPearls — Cardiac arrhythmia classification"
        },
        # THÊM MỚI
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK482154/",
            "slug": "statpearls_heart_failure", "chunk_type": "DISEASE", "severity": "URGENT",
            "note": "StatPearls — Heart failure classification HFrEF/HFpEF"
        },
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK459364/",
            "slug": "statpearls_hypertension", "chunk_type": "DISEASE", "severity": "URGENT",
            "note": "StatPearls — Hypertension staging and management"
        },
        {
            "url": "https://www.mdcalc.com/calc/801/cha2ds2-vasc-score-atrial-fibrillation-stroke-risk",
            "slug": "chads_vasc_score", "chunk_type": "GUIDELINE", "severity": "URGENT",
            "note": "CHA2DS2-VASc score — AF stroke risk calculator"
        },
    ],

    "nephrology_endocrinology": [
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK535404/",
            "slug": "dept_overview_ckd", "chunk_type": "DEPARTMENT", "severity": "ROUTINE",
            "note": "CKD overview: staging, GFR, KDIGO"
        },
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK441876/",
            "slug": "disease_ckd_staging", "chunk_type": "DISEASE", "severity": "URGENT",
            "note": "CKD staging G1-G5 with GFR thresholds"
        },
        {
            "url": "https://www.testing.com/tests/creatinine/",
            "slug": "lab_creatinine_range", "chunk_type": "GUIDELINE", "severity": "ROUTINE",
            "note": "Creatinine normal range"
        },
        {
            "url": "https://www.testing.com/tests/estimated-glomerular-filtration-rate-egfr/",
            "slug": "lab_egfr_range", "chunk_type": "GUIDELINE", "severity": "URGENT",
            "note": "eGFR normal range — CKD stage mapping"
        },
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK551501/",
            "slug": "disease_diabetes_type2", "chunk_type": "DISEASE", "severity": "URGENT",
            "note": "Type 2 diabetes diagnostic criteria"
        },
        {
            "url": "https://www.testing.com/tests/hemoglobin-a1c/",
            "slug": "lab_hba1c_range", "chunk_type": "GUIDELINE", "severity": "URGENT",
            "note": "HbA1c ranges — normal/prediabetes/diabetes"
        },
        {
            "url": "https://www.testing.com/tests/glucose/",
            "slug": "lab_glucose_range", "chunk_type": "GUIDELINE", "severity": "URGENT",
            "note": "Fasting glucose ranges"
        },
    ],

    "hematology_internal": [
        {
            "url": "https://en.wikipedia.org/wiki/Hematology",
            "slug": "dept_overview_hematology", "chunk_type": "DEPARTMENT", "severity": "ROUTINE",
            "note": "Hematology overview and anemia classification"
        },
        {
            "url": "https://www.testing.com/tests/white-blood-cell-count-wbc/",
            "slug": "lab_wbc_range", "chunk_type": "GUIDELINE", "severity": "URGENT",
            "note": "WBC normal range"
        },
        {
            "url": "https://www.testing.com/tests/hemoglobin/",
            "slug": "lab_hemoglobin_range", "chunk_type": "GUIDELINE", "severity": "URGENT",
            "note": "Hemoglobin — anemia grading WHO"
        },
        {
            "url": "https://www.testing.com/tests/mean-corpuscular-volume-mcv/",
            "slug": "lab_mcv_range", "chunk_type": "GUIDELINE", "severity": "ROUTINE",
            "note": "MCV — microcytic vs macrocytic anemia"
        },
        {
            "url": "https://www.testing.com/tests/platelet-count/",
            "slug": "lab_platelet_range", "chunk_type": "GUIDELINE", "severity": "URGENT",
            "note": "Platelets normal range"
        },
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK448065/",
            "slug": "disease_iron_deficiency_anemia", "chunk_type": "DISEASE", "severity": "URGENT",
            "note": "Iron deficiency anemia: low MCV, low ferritin"
        },
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK560705/",
            "slug": "disease_leukemia_cbc_pattern", "chunk_type": "DISEASE", "severity": "EMERGENCY",
            "note": "Leukemia CBC pattern: extreme leukocytosis"
        },
        {
            "url": "https://www.testing.com/tests/complete-blood-count/",
            "slug": "cbc_interpretation_guide", "chunk_type": "GUIDELINE", "severity": "ROUTINE",
            "note": "Full blood count interpretation guide"
        },
    ],
}

# ---------------------------------------------------------------------------
# COLLECTION 1: CLINICAL — Guidelines PDFs (MỚI)
# Tất cả đều có direct PDF URL, free, no login required
# ---------------------------------------------------------------------------

CLINICAL_PDFS = [

    # ── CARDIOLOGY ──────────────────────────────────────────────────────────
    {
        "slug": "esc_2024_chronic_coronary_syndromes",
        "dept": "cardiology",
        "severity": "URGENT",
        "chunk_type": "GUIDELINE",
        "url": "https://www.escardio.org/Guidelines/Clinical-Practice-Guidelines/Chronic-Coronary-Syndromes",
        "note": "ESC 2024 — Chronic Coronary Syndromes guideline summary",
        "size_hint": "web summary, use Jina",
        "fetch_mode": "jina"
    },
    {
        "slug": "esc_2023_atrial_fibrillation",
        "dept": "cardiology",
        "severity": "URGENT",
        "chunk_type": "GUIDELINE",
        "url": "https://www.escardio.org/Guidelines/Clinical-Practice-Guidelines/Atrial-Fibrillation-Management",
        "note": "ESC 2024 — Atrial Fibrillation AF-CARE framework",
        "size_hint": "web summary, use Jina",
        "fetch_mode": "jina"
    },
    {
        "slug": "esc_2023_acute_coronary_syndromes",
        "dept": "cardiology",
        "severity": "EMERGENCY",
        "chunk_type": "GUIDELINE",
        "url": "https://icus-society.org/wp-content/uploads/2024/09/ESCCCS-2024-guideline7.pdf",
        "note": "ESC 2024 — Chronic Coronary Syndromes (mirror PDF)",
        "size_hint": "~120 pages"
    },
    {
        "slug": "esc_2024_hypertension",
        "dept": "cardiology",
        "severity": "URGENT",
        "chunk_type": "GUIDELINE",
        "url": "https://www.escardio.org/Guidelines/Clinical-Practice-Guidelines/Hypertension",
        "note": "ESC 2023 — Hypertension management guideline summary",
        "size_hint": "web summary, use Jina",
        "fetch_mode": "jina"
    },

    # ── NEPHROLOGY / ENDOCRINOLOGY ───────────────────────────────────────────
    {
        "slug": "kdigo_2024_ckd_full",
        "dept": "nephrology_endocrinology",
        "severity": "URGENT",
        "chunk_type": "GUIDELINE",
        "url": "https://kdigo.org/wp-content/uploads/2024/03/KDIGO-2024-CKD-Guideline.pdf",
        "note": "KDIGO 2024 — CKD Evaluation & Management (full guideline)",
        "size_hint": "~200 pages"
    },
    {
        "slug": "kdigo_2024_ckd_executive_summary",
        "dept": "nephrology_endocrinology",
        "severity": "URGENT",
        "chunk_type": "GUIDELINE",
        "url": "https://kdigo.org/wp-content/uploads/2017/02/KDIGO-2024-CKD-Guideline-Executive-Summary.pdf",
        "note": "KDIGO 2024 — CKD Executive Summary (concise version for RAG)",
        "size_hint": "~30 pages"
    },
    {
        "slug": "ada_2024_standards_of_care",
        "dept": "nephrology_endocrinology",
        "severity": "URGENT",
        "chunk_type": "GUIDELINE",
        "url": "https://aladlatam.org/wp-content/uploads/2024/01/standards-of-care-2024.pdf",
        "note": "ADA 2024 — Standards of Care in Diabetes (full supplement)",
        "size_hint": "~250 pages"
    },

    # ── RESPIRATORY ──────────────────────────────────────────────────────────
    {
        "slug": "who_2022_pneumonia_treatment",
        "dept": "respiratory",
        "severity": "URGENT",
        "chunk_type": "GUIDELINE",
        "url": "https://www.who.int/publications/i/item/9789240057890",
        "note": "WHO 2022 — Consolidated guidelines on pneumonia treatment",
        "size_hint": "web page, use Jina",
        "fetch_mode": "jina"
    },
    {
        "slug": "gold_2024_copd_report",
        "dept": "respiratory",
        "severity": "URGENT",
        "chunk_type": "GUIDELINE",
        "url": "https://goldcopd.org/2024-gold-report/",
        "note": "GOLD 2024 — COPD Global Strategy Report (fetch via Jina — PDF not direct)",
        "size_hint": "web page, use Jina",
        "fetch_mode": "jina"  # dùng Jina thay vì download PDF
    },

    # ── NEUROLOGY ────────────────────────────────────────────────────────────
    {
        "slug": "who_brain_tumor_classification_2022",
        "dept": "neurology",
        "severity": "URGENT",
        "chunk_type": "GUIDELINE",
        "url": "https://www.ncbi.nlm.nih.gov/books/NBK441861/",
        "note": "WHO CNS tumor classification 2021 — StatPearls overview",
        "size_hint": "web, use Jina",
        "fetch_mode": "jina"
    },

    # ── OPHTHALMOLOGY ────────────────────────────────────────────────────────
    {
        "slug": "idf_2023_diabetes_atlas_retinopathy",
        "dept": "ophthalmology",
        "severity": "ROUTINE",
        "chunk_type": "GUIDELINE",
        "url": "https://diabetesatlas.org/en/sections/complications-of-diabetes/",
        "note": "IDF Diabetes Atlas — Diabetes complications including retinopathy",
        "size_hint": "web page, use Jina",
        "fetch_mode": "jina"
    },

    # ── HEMATOLOGY ───────────────────────────────────────────────────────────
    {
        "slug": "who_2020_hb_anemia_thresholds",
        "dept": "hematology_internal",
        "severity": "ROUTINE",
        "chunk_type": "GUIDELINE",
        "url": "https://www.who.int/publications/i/item/9789240000339",
        "note": "WHO 2020 — Haemoglobin concentrations for anaemia diagnosis",
        "size_hint": "web, use Jina",
        "fetch_mode": "jina"
    },
]

# ---------------------------------------------------------------------------
# COLLECTION 2: PATIENT — MedlinePlus API (MỚI)
# plain language, viết cho bệnh nhân, UC1 triage + UC4 explain
# API: https://wsearch.nlm.nih.gov/ws/query?db=healthTopics&term=<term>
# Rate limit: 85 req/min
# ---------------------------------------------------------------------------

MEDLINEPLUS_TOPICS = [
    # Respiratory
    {"term": "pneumonia",            "slug": "pt_pneumonia",         "dept": "respiratory"},
    {"term": "asthma",               "slug": "pt_asthma",            "dept": "respiratory"},
    {"term": "COPD",                 "slug": "pt_copd",              "dept": "respiratory"},
    {"term": "bronchitis",           "slug": "pt_bronchitis",        "dept": "respiratory"},
    {"term": "shortness of breath",  "slug": "pt_dyspnea",          "dept": "respiratory"},
    {"term": "cough",                "slug": "pt_cough",             "dept": "respiratory"},
    {"term": "chest pain",           "slug": "pt_chest_pain",        "dept": "respiratory"},

    # Dermatology
    {"term": "melanoma",             "slug": "pt_melanoma",          "dept": "dermatology"},
    {"term": "skin cancer",          "slug": "pt_skin_cancer",       "dept": "dermatology"},
    {"term": "mole",                 "slug": "pt_mole",              "dept": "dermatology"},
    {"term": "basal cell carcinoma", "slug": "pt_bcc",               "dept": "dermatology"},
    {"term": "skin rash",            "slug": "pt_skin_rash",         "dept": "dermatology"},

    # Neurology
    {"term": "brain tumor",          "slug": "pt_brain_tumor",       "dept": "neurology"},
    {"term": "glioma",               "slug": "pt_glioma",            "dept": "neurology"},
    {"term": "meningioma",           "slug": "pt_meningioma",        "dept": "neurology"},
    {"term": "headache",             "slug": "pt_headache",          "dept": "neurology"},
    {"term": "seizure",              "slug": "pt_seizure",           "dept": "neurology"},

    # Ophthalmology
    {"term": "diabetic retinopathy", "slug": "pt_diabetic_retinopathy", "dept": "ophthalmology"},
    {"term": "vision loss",          "slug": "pt_vision_loss",       "dept": "ophthalmology"},
    {"term": "blurry vision",        "slug": "pt_blurry_vision",     "dept": "ophthalmology"},

    # Cardiology
    {"term": "atrial fibrillation",  "slug": "pt_afib",              "dept": "cardiology"},
    {"term": "heart failure",        "slug": "pt_heart_failure",     "dept": "cardiology"},
    {"term": "arrhythmia",           "slug": "pt_arrhythmia",        "dept": "cardiology"},
    {"term": "heart attack",         "slug": "pt_heart_attack",      "dept": "cardiology"},
    {"term": "high blood pressure",  "slug": "pt_hypertension",      "dept": "cardiology"},
    {"term": "palpitations",         "slug": "pt_palpitations",      "dept": "cardiology"},

    # Nephrology/Endocrinology
    {"term": "chronic kidney disease", "slug": "pt_ckd",             "dept": "nephrology_endocrinology"},
    {"term": "diabetes type 2",      "slug": "pt_diabetes_t2",       "dept": "nephrology_endocrinology"},
    {"term": "prediabetes",          "slug": "pt_prediabetes",       "dept": "nephrology_endocrinology"},
    {"term": "kidney failure",       "slug": "pt_kidney_failure",    "dept": "nephrology_endocrinology"},
    {"term": "blood sugar",          "slug": "pt_blood_sugar",       "dept": "nephrology_endocrinology"},

    # Hematology/Internal
    {"term": "anemia",               "slug": "pt_anemia",            "dept": "hematology_internal"},
    {"term": "iron deficiency anemia", "slug": "pt_iron_deficiency", "dept": "hematology_internal"},
    {"term": "white blood cells",    "slug": "pt_wbc",               "dept": "hematology_internal"},
    {"term": "leukemia",             "slug": "pt_leukemia",          "dept": "hematology_internal"},
    {"term": "fatigue",              "slug": "pt_fatigue",           "dept": "hematology_internal"},

    # Triage / General symptoms (cho UC1 — tiếp tân AI điều hướng)
    {"term": "fever",                "slug": "pt_fever",             "dept": "triage"},
    {"term": "nausea vomiting",      "slug": "pt_nausea_vomiting",   "dept": "triage"},
    {"term": "abdominal pain",       "slug": "pt_abdominal_pain",    "dept": "triage"},
    {"term": "dizziness",            "slug": "pt_dizziness",         "dept": "triage"},
    {"term": "weight loss",          "slug": "pt_weight_loss",       "dept": "triage"},
    {"term": "swelling edema",       "slug": "pt_edema",             "dept": "triage"},
    {"term": "night sweats",         "slug": "pt_night_sweats",      "dept": "triage"},
]

# ---------------------------------------------------------------------------
# Core fetch functions
# ---------------------------------------------------------------------------

def setup_directories():
    """Tạo cấu trúc thư mục output."""
    dirs = [PDF_DIR, MEDLINEPLUS_DIR]
    for dept in CLINICAL_WEB:
        dirs.append(os.path.join(CLINICAL_DIR, dept))
    for entry in MEDLINEPLUS_TOPICS:
        dept_dir = os.path.join(MEDLINEPLUS_DIR, entry["dept"])
        if dept_dir not in dirs:
            dirs.append(dept_dir)
    for d in dirs:
        os.makedirs(d, exist_ok=True)
    print(f"[INFO] Output: {OUTPUT_DIR}/")


def build_frontmatter(slug, dept, url, chunk_type, severity, note, source="web") -> str:
    return f"""---
source_url: {url}
source_type: {source}
department: {dept}
chunk_type: {chunk_type}
severity: {severity}
slug: {slug}
note: {note}
fetched_at: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}
---

"""


def fetch_via_jina(url: str) -> str | None:
    """Fetch URL content qua Jina Reader API (web articles → markdown)."""
    jina_url = f"{JINA_BASE}{url}"
    headers = {"Accept": "text/markdown", "Authorization": f"Bearer {JINA_API_KEY}"}
    for attempt in range(1, MAX_RETRIES + 2):
        try:
            r = requests.get(jina_url, timeout=REQUEST_TIMEOUT, headers=headers)
            if r.status_code == 200:
                return r.text
            print(f"     ⚠️  HTTP {r.status_code} (attempt {attempt})")
        except requests.exceptions.Timeout:
            print(f"     ⚠️  Timeout (attempt {attempt})")
        except requests.exceptions.RequestException as e:
            print(f"     ⚠️  Error: {e} (attempt {attempt})")
        if attempt <= MAX_RETRIES:
            time.sleep(3)
    return None


def download_pdf(url: str, dest_path: str) -> bool:
    """Download PDF trực tiếp về file."""
    headers = {"User-Agent": "Mozilla/5.0 (HealthAI Research Bot)"}
    for attempt in range(1, MAX_RETRIES + 2):
        try:
            r = requests.get(url, timeout=REQUEST_TIMEOUT, headers=headers, stream=True)
            if r.status_code == 200 and "pdf" in r.headers.get("Content-Type", "").lower():
                with open(dest_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                size_kb = os.path.getsize(dest_path) // 1024
                print(f"     ✅ PDF saved: {dest_path} ({size_kb:,} KB)")
                return True
            elif r.status_code == 200:
                # Thử dùng Jina nếu response không phải PDF
                print(f"     ⚠️  Response not PDF (Content-Type: {r.headers.get('Content-Type', 'unknown')}), will try Jina")
                return False
            else:
                print(f"     ⚠️  HTTP {r.status_code} (attempt {attempt})")
        except Exception as e:
            print(f"     ⚠️  Error: {e} (attempt {attempt})")
        if attempt <= MAX_RETRIES:
            time.sleep(3)
    return False


def fetch_medlineplus(term: str) -> dict | None:
    """
    Gọi MedlinePlus Web Service API.
    Returns dict với title, summary, url — plain language cho bệnh nhân.
    """
    api_url = f"https://wsearch.nlm.nih.gov/ws/query"
    params = {"db": "healthTopics", "term": term, "retmax": "1"}
    try:
        r = requests.get(api_url, params=params, timeout=30)
        if r.status_code != 200:
            print(f"     ⚠️  MedlinePlus API HTTP {r.status_code}")
            return None

        # Parse XML response
        import xml.etree.ElementTree as ET
        root = ET.fromstring(r.text)

        result = {"term": term, "documents": []}
        for doc in root.findall(".//document"):
            url_elem = doc.find("./content[@name='org.url']")
            title_elem = doc.find("./content[@name='title']")
            summary_elem = doc.find("./content[@name='FullSummary']")

            entry = {
                "url":     url_elem.text.strip()    if url_elem     is not None else "",
                "title":   _strip_tags(title_elem.text)   if title_elem   is not None else term,
                "summary": _strip_tags(summary_elem.text) if summary_elem is not None else "",
            }
            result["documents"].append(entry)
        return result

    except Exception as e:
        print(f"     ⚠️  MedlinePlus error: {e}")
        return None


def _strip_tags(text: str) -> str:
    """Xóa HTML tags khỏi text."""
    import re
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text).strip()


def save_text(content: str, path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ---------------------------------------------------------------------------
# Pipeline functions
# ---------------------------------------------------------------------------

def run_clinical_web(dept_filter: str | None = None, dry_run: bool = False):
    """Fetch web articles cho clinical collection (dùng Jina)."""
    target = {dept_filter: CLINICAL_WEB[dept_filter]} if dept_filter else CLINICAL_WEB
    stats = {"success": 0, "failed": 0, "skipped": 0}

    print("\n" + "="*60)
    print("  CLINICAL — Web Articles (Jina Reader)")
    print("="*60)

    for dept, entries in target.items():
        print(f"\n── {dept.upper()} ({len(entries)} articles) ──")
        for i, entry in enumerate(entries, 1):
            url   = entry["url"]
            slug  = entry["slug"]
            path  = os.path.join(CLINICAL_DIR, dept, f"{slug}.md")

            print(f"\n  [{i}/{len(entries)}] {slug}")

            if os.path.exists(path):
                print("     Already exists — skip")
                stats["skipped"] += 1
                continue

            if dry_run:
                print(f"     [DRY RUN] → {path}")
                stats["success"] += 1
                continue

            content = fetch_via_jina(url)
            if content:
                fm = build_frontmatter(slug, dept, url,
                                       entry.get("chunk_type", "GUIDELINE"),
                                       entry.get("severity", "ROUTINE"),
                                       entry.get("note", ""), source="jina_web")
                save_text(fm + content, path)
                print(f"     ✅ Saved ({len(content):,} chars)")
                stats["success"] += 1
            else:
                print(f"     ❌ Failed")
                stats["failed"] += 1

            time.sleep(SLEEP_WEB)

    return stats


def run_clinical_pdfs(dry_run: bool = False):
    """Download PDF guidelines cho clinical collection."""
    stats = {"success": 0, "failed": 0, "skipped": 0}

    print("\n" + "="*60)
    print("  CLINICAL — Guidelines PDFs")
    print("="*60)

    for i, entry in enumerate(CLINICAL_PDFS, 1):
        slug      = entry["slug"]
        dept      = entry["dept"]
        url       = entry["url"]
        fetch_mode = entry.get("fetch_mode", "pdf")

        # PDF lưu theo dept, markdown từ Jina cũng lưu theo dept
        if fetch_mode == "pdf":
            dest = os.path.join(PDF_DIR, f"{slug}.pdf")
        else:
            dest = os.path.join(CLINICAL_DIR, dept, f"{slug}.md")

        print(f"\n  [{i}/{len(CLINICAL_PDFS)}] {slug}")
        print(f"     Mode: {fetch_mode.upper()} | {entry.get('size_hint', '')}")
        print(f"     URL: {url}")

        if os.path.exists(dest):
            print("     Already exists — skip")
            stats["skipped"] += 1
            continue

        if dry_run:
            print(f"     [DRY RUN] → {dest}")
            stats["success"] += 1
            continue

        if fetch_mode == "pdf":
            ok = download_pdf(url, dest)
            if not ok:
                # Fallback: thử Jina
                print("     Falling back to Jina...")
                md_path = dest.replace(".pdf", "_jina.md")
                content = fetch_via_jina(url)
                if content:
                    fm = build_frontmatter(slug, dept, url,
                                           entry.get("chunk_type", "GUIDELINE"),
                                           entry.get("severity", "ROUTINE"),
                                           entry.get("note", ""), source="jina_fallback")
                    save_text(fm + content, md_path)
                    print(f"     ✅ Jina fallback saved")
                    ok = True
            stats["success" if ok else "failed"] += 1
        else:
            content = fetch_via_jina(url)
            if content:
                fm = build_frontmatter(slug, dept, url,
                                       entry.get("chunk_type", "GUIDELINE"),
                                       entry.get("severity", "ROUTINE"),
                                       entry.get("note", ""), source="jina_web")
                save_text(fm + content, dest)
                print(f"     ✅ Saved ({len(content):,} chars)")
                stats["success"] += 1
            else:
                print(f"     ❌ Failed")
                stats["failed"] += 1

        time.sleep(SLEEP_PDF)

    return stats


def run_patient_medlineplus(dry_run: bool = False):
    """Fetch patient education content từ MedlinePlus API."""
    stats = {"success": 0, "failed": 0, "skipped": 0}

    print("\n" + "="*60)
    print("  PATIENT — MedlinePlus API (NIH plain language)")
    print("="*60)

    for i, topic in enumerate(MEDLINEPLUS_TOPICS, 1):
        term  = topic["term"]
        slug  = topic["slug"]
        dept  = topic["dept"]
        path  = os.path.join(MEDLINEPLUS_DIR, dept, f"{slug}.md")

        print(f"\n  [{i}/{len(MEDLINEPLUS_TOPICS)}] {slug} (term: \"{term}\")")

        if os.path.exists(path):
            print("     Already exists — skip")
            stats["skipped"] += 1
            continue

        if dry_run:
            print(f"     [DRY RUN] → {path}")
            stats["success"] += 1
            continue

        data = fetch_medlineplus(term)
        if data and data["documents"]:
            doc = data["documents"][0]
            fm = build_frontmatter(slug, dept, doc["url"],
                                   "PATIENT_EDUCATION", "ROUTINE",
                                   f"MedlinePlus — {doc['title']}",
                                   source="medlineplus_api")
            content = f"# {doc['title']}\n\n**Source:** {doc['url']}\n\n{doc['summary']}\n"
            save_text(fm + content, path)
            words = len(doc["summary"].split())
            print(f"     ✅ Saved ({words} words)")
            stats["success"] += 1
        else:
            print(f"     ❌ No result / Failed")
            stats["failed"] += 1

        time.sleep(SLEEP_API)

    return stats


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="HealthAI v2 — Medical Knowledge Base Ingestion Pipeline"
    )
    parser.add_argument("--collection", choices=["clinical", "patient", "all"],
                        default="all", help="Which collection to fetch")
    parser.add_argument("--mode", choices=["web", "pdfs", "all"], default="all",
                        help="For clinical: web articles, PDFs, or both")
    parser.add_argument("--dept", type=str, default=None,
                        help="Filter clinical web articles by department")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print plan without fetching")
    args = parser.parse_args()

    if args.dept and args.dept not in CLINICAL_WEB:
        print(f"❌ Unknown department: {args.dept}")
        print(f"   Available: {', '.join(CLINICAL_WEB.keys())}")
        return

    total_web  = sum(len(v) for v in CLINICAL_WEB.values())
    total_pdfs = len(CLINICAL_PDFS)
    total_pt   = len(MEDLINEPLUS_TOPICS)

    print("\n" + "="*60)
    print("  HealthAI v2 — Knowledge Base Ingestion Pipeline")
    print("="*60)
    print(f"  Clinical web articles : {total_web}")
    print(f"  Clinical PDF guidelines: {total_pdfs}")
    print(f"  Patient MedlinePlus   : {total_pt}")
    print(f"  Collection: {args.collection} | Mode: {args.mode}")
    if args.dry_run:
        print("  Mode: DRY RUN")
    print("="*60)

    setup_directories()

    overall = {"success": 0, "failed": 0, "skipped": 0}

    def merge(s):
        for k in overall:
            overall[k] += s[k]

    if args.collection in ("clinical", "all"):
        if args.mode in ("web", "all"):
            merge(run_clinical_web(dept_filter=args.dept, dry_run=args.dry_run))
        if args.mode in ("pdfs", "all") and not args.dept:
            merge(run_clinical_pdfs(dry_run=args.dry_run))

    if args.collection in ("patient", "all") and not args.dept:
        merge(run_patient_medlineplus(dry_run=args.dry_run))

    print("\n" + "="*60)
    print("  PIPELINE COMPLETE")
    print("="*60)
    print(f"  ✅ Success : {overall['success']}")
    print(f"  ⏭️  Skipped : {overall['skipped']} (already exists)")
    print(f"  ❌ Failed  : {overall['failed']}")
    print(f"\n  Output: ./{OUTPUT_DIR}/")
    print("  Cấu trúc:")
    print("    clinical/guidelines_pdf/   ← PDF lớn (ESC, ADA, KDIGO)")
    print("    clinical/<dept>/           ← Web articles (Jina)")
    print("    patient/medlineplus/<dept>/← Plain language (NIH API)")
    print("\n  Next: chạy chunker.py để split thành RAG-ready chunks\n")


if __name__ == "__main__":
    main()