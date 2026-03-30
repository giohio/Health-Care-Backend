"""
HealthAI Portal — Medical Knowledge Base Ingestion Pipeline
============================================================
Fetches clinical guidelines from authoritative sources via Jina Reader API,
saves clean Markdown files organized by department, ready for RAG chunking.

Usage:
    pip install requests
    python fetch_knowledge_base.py

    # Fetch specific department only:
    python fetch_knowledge_base.py --dept respiratory

    # Dry run (print URLs without fetching):
    python fetch_knowledge_base.py --dry-run

Output structure:
    rag_knowledge_base/
    ├── respiratory/
    ├── dermatology/
    ├── neurology/
    ├── ophthalmology/
    ├── cardiology/
    ├── nephrology_endocrinology/
    └── hematology_internal/
"""

import os
import time
import argparse
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OUTPUT_DIR = "rag_knowledge_base"
JINA_BASE = "https://r.jina.ai/"
REQUEST_TIMEOUT = 45
SLEEP_BETWEEN_REQUESTS = 2.5  # seconds — respect rate limits
MAX_RETRIES = 2

JINA_API_KEY = os.getenv("JINA_API_KEY")
if not JINA_API_KEY:
    raise EnvironmentError("JINA_API_KEY environment variable is not set.")
# ---------------------------------------------------------------------------
# Knowledge Base URL Registry
# 7 departments, each with department-level and disease-level sources.
# To add more articles: append to the list under the right department.
# ---------------------------------------------------------------------------

KNOWLEDGE_BASE = {

    # -----------------------------------------------------------------------
    # 1. RESPIRATORY — Chest X-Ray + Respiratory Sounds
    #    Datasets: Chest X-Ray Pneumonia, Respiratory Sound Dataset
    # -----------------------------------------------------------------------
    "respiratory": [
        # Department overview
        {
            "url": "https://www.merckmanuals.com/professional/pulmonary-disorders/approach-to-the-pulmonary-patient/overview-of-pulmonary-disorders",
            "slug": "dept_overview_pulmonary",
            "chunk_type": "DEPARTMENT",
            "severity": "ROUTINE",
            "note": "Pulmonary department overview — clinical approach"
        },
        # Diseases
        {
            "url": "https://radiopaedia.org/articles/pneumonia",
            "slug": "disease_pneumonia_radiology",
            "chunk_type": "DISEASE",
            "severity": "URGENT",
            "note": "Pneumonia — radiological findings, X-ray patterns"
        },
        {
            "url": "https://radiopaedia.org/articles/lobar-pneumonia",
            "slug": "disease_lobar_pneumonia",
            "chunk_type": "DISEASE",
            "severity": "URGENT",
            "note": "Lobar pneumonia — consolidation patterns on CXR"
        },
        {
            "url": "https://radiopaedia.org/articles/bronchopneumonia",
            "slug": "disease_bronchopneumonia",
            "chunk_type": "DISEASE",
            "severity": "URGENT",
            "note": "Bronchopneumonia — patchy opacities, bilateral involvement"
        },
        {
            "url": "https://radiopaedia.org/articles/normal-chest-radiograph",
            "slug": "normal_chest_xray_anatomy",
            "chunk_type": "GUIDELINE",
            "severity": "ROUTINE",
            "note": "Normal chest X-ray — baseline anatomy for comparison"
        },
        {
            "url": "https://litfl.com/pneumonia-ecg-library/",
            "slug": "pneumonia_clinical_emergency",
            "chunk_type": "GUIDELINE",
            "severity": "URGENT",
            "note": "Pneumonia emergency criteria — red flags"
        },
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK430685/",
            "slug": "statpearls_pneumonia",
            "chunk_type": "DISEASE",
            "severity": "URGENT",
            "note": "StatPearls — Community-acquired pneumonia etiology and diagnosis"
        },
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK559109/",
            "slug": "statpearls_asthma",
            "chunk_type": "DISEASE",
            "severity": "URGENT",
            "note": "StatPearls — Asthma clinical features and spirometry"
        },
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK482408/",
            "slug": "statpearls_copd",
            "chunk_type": "DISEASE",
            "severity": "URGENT",
            "note": "StatPearls — COPD diagnosis and GOLD classification"
        },
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK513273/",
            "slug": "statpearls_bronchitis",
            "chunk_type": "DISEASE",
            "severity": "ROUTINE",
            "note": "StatPearls — Acute bronchitis vs chronic bronchitis"
        },
        # Differential diagnosis
        {
            "url": "https://radiopaedia.org/articles/chest-x-ray-an-approach",
            "slug": "cxr_systematic_approach",
            "chunk_type": "GUIDELINE",
            "severity": "ROUTINE",
            "note": "Systematic CXR reading approach — for Vision LLM prompt alignment"
        },
        {
            "url": "https://radiopaedia.org/articles/pulmonary-opacity",
            "slug": "differential_pulmonary_opacity",
            "chunk_type": "GUIDELINE",
            "severity": "ROUTINE",
            "note": "Pulmonary opacity differential — consolidation vs ground-glass vs atelectasis"
        },
    ],

    # -----------------------------------------------------------------------
    # 2. DERMATOLOGY — HAM10000 (7 skin lesion classes)
    #    Classes: MEL, NV, BCC, AK, BKL, DF, VASC
    # -----------------------------------------------------------------------
    "dermatology": [
        {
            "url": "https://dermnetnz.org/topics/dermoscopy",
            "slug": "dept_overview_dermoscopy",
            "chunk_type": "DEPARTMENT",
            "severity": "ROUTINE",
            "note": "Dermoscopy overview — how to read skin lesion images"
        },
        {
            "url": "https://dermnetnz.org/topics/melanoma",
            "slug": "disease_melanoma",
            "chunk_type": "DISEASE",
            "severity": "EMERGENCY",
            "note": "Melanoma — ABCDE criteria, dermoscopic features"
        },
        {
            "url": "https://dermnetnz.org/topics/melanocytic-naevus",
            "slug": "disease_melanocytic_naevus",
            "chunk_type": "DISEASE",
            "severity": "ROUTINE",
            "note": "Benign melanocytic naevus (NV) — normal mole features"
        },
        {
            "url": "https://dermnetnz.org/topics/basal-cell-carcinoma",
            "slug": "disease_bcc",
            "chunk_type": "DISEASE",
            "severity": "URGENT",
            "note": "Basal cell carcinoma (BCC) — pearly papule, telangiectasia"
        },
        {
            "url": "https://dermnetnz.org/topics/actinic-keratosis",
            "slug": "disease_actinic_keratosis",
            "chunk_type": "DISEASE",
            "severity": "URGENT",
            "note": "Actinic keratosis (AK) — scaly patch, sun-damaged skin"
        },
        {
            "url": "https://dermnetnz.org/topics/seborrhoeic-keratosis",
            "slug": "disease_seborrhoeic_keratosis",
            "chunk_type": "DISEASE",
            "severity": "ROUTINE",
            "note": "Seborrhoeic keratosis (BKL) — stuck-on appearance, benign"
        },
        {
            "url": "https://dermnetnz.org/topics/dermatofibroma",
            "slug": "disease_dermatofibroma",
            "chunk_type": "DISEASE",
            "severity": "ROUTINE",
            "note": "Dermatofibroma (DF) — firm papule, dimple sign"
        },
        {
            "url": "https://dermnetnz.org/topics/vascular-lesions-of-the-skin",
            "slug": "disease_vascular_lesion",
            "chunk_type": "DISEASE",
            "severity": "ROUTINE",
            "note": "Vascular lesions (VASC) — haemangioma, pyogenic granuloma"
        },
        {
            "url": "https://dermnetnz.org/topics/how-to-diagnose-skin-lesions",
            "slug": "differential_skin_lesion_diagnosis",
            "chunk_type": "GUIDELINE",
            "severity": "ROUTINE",
            "note": "Skin lesion differential diagnosis approach"
        },
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK470538/",
            "slug": "statpearls_melanoma",
            "chunk_type": "DISEASE",
            "severity": "EMERGENCY",
            "note": "StatPearls — Melanoma staging and prognosis"
        },
    ],

    # -----------------------------------------------------------------------
    # 3. NEUROLOGY & IMAGING — Brain Tumor MRI
    #    Classes: Glioma, Meningioma, Pituitary Tumor, No Tumor
    # -----------------------------------------------------------------------
    "neurology": [
        {
            "url": "https://radiopaedia.org/articles/brain-mri-an-approach",
            "slug": "dept_overview_brain_mri",
            "chunk_type": "DEPARTMENT",
            "severity": "ROUTINE",
            "note": "Brain MRI systematic reading approach"
        },
        {
            "url": "https://radiopaedia.org/articles/normal-brain-mri-anatomy",
            "slug": "normal_brain_mri",
            "chunk_type": "GUIDELINE",
            "severity": "ROUTINE",
            "note": "Normal brain MRI — baseline anatomy for comparison"
        },
        {
            "url": "https://radiopaedia.org/articles/glioma",
            "slug": "disease_glioma",
            "chunk_type": "DISEASE",
            "severity": "EMERGENCY",
            "note": "Glioma — MRI signal characteristics, infiltrative pattern"
        },
        {
            "url": "https://radiopaedia.org/articles/glioblastoma-idh-wildtype",
            "slug": "disease_glioblastoma",
            "chunk_type": "DISEASE",
            "severity": "EMERGENCY",
            "note": "Glioblastoma — ring enhancement, heterogeneous signal"
        },
        {
            "url": "https://radiopaedia.org/articles/meningioma",
            "slug": "disease_meningioma",
            "chunk_type": "DISEASE",
            "severity": "URGENT",
            "note": "Meningioma — dural tail, extra-axial mass, homogeneous enhancement"
        },
        {
            "url": "https://radiopaedia.org/articles/pituitary-adenoma",
            "slug": "disease_pituitary_adenoma",
            "chunk_type": "DISEASE",
            "severity": "URGENT",
            "note": "Pituitary adenoma — sellar mass, micro vs macro classification"
        },
        {
            "url": "https://radiopaedia.org/articles/intra-axial-brain-tumours",
            "slug": "differential_brain_tumors",
            "chunk_type": "GUIDELINE",
            "severity": "URGENT",
            "note": "Brain tumor differential — intra-axial vs extra-axial distinction"
        },
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK441861/",
            "slug": "statpearls_brain_tumor",
            "chunk_type": "DISEASE",
            "severity": "EMERGENCY",
            "note": "StatPearls — Brain tumor classification and clinical features"
        },
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK470578/",
            "slug": "statpearls_meningioma",
            "chunk_type": "DISEASE",
            "severity": "URGENT",
            "note": "StatPearls — Meningioma epidemiology and WHO grading"
        },
    ],

    # -----------------------------------------------------------------------
    # 4. OPHTHALMOLOGY — APTOS 2019 Diabetic Retinopathy
    #    Classes: Grade 0 (No DR) to Grade 4 (Proliferative DR)
    # -----------------------------------------------------------------------
    "ophthalmology": [
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK560805/",
            "slug": "dept_overview_diabetic_retinopathy",
            "chunk_type": "DEPARTMENT",
            "severity": "ROUTINE",
            "note": "Diabetic retinopathy overview — pathophysiology and staging"
        },
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK431054/",
            "slug": "disease_dr_grade_mild",
            "chunk_type": "DISEASE",
            "severity": "ROUTINE",
            "note": "Mild NPDR — microaneurysms only, grade 1 criteria"
        },
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK507836/",
            "slug": "disease_dr_grade_moderate_severe",
            "chunk_type": "DISEASE",
            "severity": "URGENT",
            "note": "Moderate to Severe NPDR — hemorrhages, venous beading, IRMA"
        },
        {
            "url": "https://radiopaedia.org/articles/proliferative-diabetic-retinopathy",
            "slug": "disease_proliferative_dr",
            "chunk_type": "DISEASE",
            "severity": "EMERGENCY",
            "note": "Proliferative DR — neovascularization, vitreous hemorrhage"
        },
        {
            "url": "https://radiopaedia.org/articles/diabetic-macular-oedema",
            "slug": "disease_diabetic_macular_edema",
            "chunk_type": "DISEASE",
            "severity": "URGENT",
            "note": "Diabetic macular edema — central vision threat, OCT findings"
        },
        {
            "url": "https://eyewiki.aao.org/Diabetic_Retinopathy",
            "slug": "aao_eyewiki_dr_classification",
            "chunk_type": "GUIDELINE",
            "severity": "ROUTINE",
            "note": "AAO EyeWiki — DR grading scale and fundus findings per grade"
        },
        {
            "url": "https://eyewiki.aao.org/Fundus_Photography",
            "slug": "fundus_photography_reading",
            "chunk_type": "GUIDELINE",
            "severity": "ROUTINE",
            "note": "Fundus photograph interpretation guide — for Vision LLM alignment"
        },
    ],

    # -----------------------------------------------------------------------
    # 5. CARDIOLOGY — ECG Heartbeat Arrhythmia
    #    Classes: Normal, AF, Other Arrhythmia, Noisy
    #    MIT-BIH Labels: N, S, V, F, Q
    # -----------------------------------------------------------------------
    "cardiology": [
        {
            "url": "https://litfl.com/ecg-library/basics/",
            "slug": "dept_overview_ecg_basics",
            "chunk_type": "DEPARTMENT",
            "severity": "ROUTINE",
            "note": "ECG basics — systematic reading: rate, rhythm, axis, intervals, morphology"
        },
        {
            "url": "https://litfl.com/ecg-library/basics/normal-ecg/",
            "slug": "normal_ecg_pattern",
            "chunk_type": "GUIDELINE",
            "severity": "ROUTINE",
            "note": "Normal ECG — baseline P/QRS/T morphology for comparison"
        },
        {
            "url": "https://litfl.com/atrial-fibrillation-ecg-library/",
            "slug": "disease_atrial_fibrillation",
            "chunk_type": "DISEASE",
            "severity": "URGENT",
            "note": "Atrial fibrillation — irregularly irregular rhythm, absent P waves"
        },
        {
            "url": "https://litfl.com/ventricular-tachycardia-monomorphic-ecg-library/",
            "slug": "disease_ventricular_tachycardia",
            "chunk_type": "DISEASE",
            "severity": "EMERGENCY",
            "note": "Ventricular tachycardia — wide complex tachycardia, AV dissociation"
        },
        {
            "url": "https://litfl.com/premature-ventricular-complex-ecg-library/",
            "slug": "disease_pvc",
            "chunk_type": "DISEASE",
            "severity": "URGENT",
            "note": "PVC (Ventricular ectopic beats) — wide bizarre QRS, compensatory pause"
        },
        {
            "url": "https://litfl.com/premature-atrial-complex-pac-ecg-library/",
            "slug": "disease_pac",
            "chunk_type": "DISEASE",
            "severity": "ROUTINE",
            "note": "PAC (Supraventricular ectopic beats) — early P wave, narrow QRS"
        },
        {
            "url": "https://litfl.com/left-bundle-branch-block-lbbb-ecg-library/",
            "slug": "disease_lbbb",
            "chunk_type": "DISEASE",
            "severity": "URGENT",
            "note": "Left bundle branch block — QRS > 120ms, broad notched R in lateral leads"
        },
        {
            "url": "https://litfl.com/st-elevation-differential-diagnosis/",
            "slug": "differential_st_elevation",
            "chunk_type": "GUIDELINE",
            "severity": "EMERGENCY",
            "note": "ST elevation differential — STEMI vs benign early repolarization"
        },
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK532939/",
            "slug": "statpearls_arrhythmia_overview",
            "chunk_type": "DISEASE",
            "severity": "URGENT",
            "note": "StatPearls — Cardiac arrhythmia classification and emergency criteria"
        },
        {
            "url": "https://ecgpedia.org/index.php/Main_Page",
            "slug": "ecgpedia_reference",
            "chunk_type": "GUIDELINE",
            "severity": "ROUTINE",
            "note": "ECGpedia — comprehensive arrhythmia reference wiki"
        },
    ],

    # -----------------------------------------------------------------------
    # 6. NEPHROLOGY & ENDOCRINOLOGY — CKD + NHANES Diabetes
    #    CKD stages 1-5 (25 features), Diabetes risk prediction
    # -----------------------------------------------------------------------
    "nephrology_endocrinology": [
        # CKD
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK535404/",
            "slug": "dept_overview_ckd",
            "chunk_type": "DEPARTMENT",
            "severity": "ROUTINE",
            "note": "StatPearls — CKD overview: staging, GFR classification, KDIGO criteria"
        },
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK441876/",
            "slug": "disease_ckd_staging",
            "chunk_type": "DISEASE",
            "severity": "URGENT",
            "note": "CKD staging G1-G5 with GFR thresholds and albuminuria categories"
        },
        {
            "url": "https://labtestsonline.org.uk/tests/creatinine-test",
            "slug": "lab_creatinine_range",
            "chunk_type": "GUIDELINE",
            "severity": "ROUTINE",
            "note": "Creatinine normal range: male 62-115, female 53-97 umol/L — interpretation"
        },
        {
            "url": "https://labtestsonline.org.uk/tests/egfr",
            "slug": "lab_egfr_range",
            "chunk_type": "GUIDELINE",
            "severity": "URGENT",
            "note": "eGFR normal range >60 ml/min/1.73m2 — CKD stage mapping"
        },
        {
            "url": "https://labtestsonline.org.uk/tests/albumin",
            "slug": "lab_albumin_range",
            "chunk_type": "GUIDELINE",
            "severity": "ROUTINE",
            "note": "Albumin/creatinine ratio — albuminuria grading A1/A2/A3"
        },
        {
            "url": "https://labtestsonline.org.uk/tests/urea-and-electrolytes",
            "slug": "lab_urea_electrolytes",
            "chunk_type": "GUIDELINE",
            "severity": "ROUTINE",
            "note": "BUN, sodium, potassium normal ranges — electrolyte interpretation"
        },
        {
            "url": "https://labtestsonline.org.uk/tests/blood-urea-nitrogen-bun",
            "slug": "lab_bun_range",
            "chunk_type": "GUIDELINE",
            "severity": "ROUTINE",
            "note": "BUN normal range 2.5-7.1 mmol/L — elevated in renal failure"
        },
        # Diabetes
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK551501/",
            "slug": "disease_diabetes_type2",
            "chunk_type": "DISEASE",
            "severity": "URGENT",
            "note": "StatPearls — Type 2 diabetes diagnostic criteria: FPG, HbA1c, OGTT"
        },
        {
            "url": "https://labtestsonline.org.uk/tests/hba1c",
            "slug": "lab_hba1c_range",
            "chunk_type": "GUIDELINE",
            "severity": "URGENT",
            "note": "HbA1c: normal <42, prediabetes 42-47, diabetes >=48 mmol/mol"
        },
        {
            "url": "https://labtestsonline.org.uk/tests/glucose-tests",
            "slug": "lab_glucose_range",
            "chunk_type": "GUIDELINE",
            "severity": "URGENT",
            "note": "Fasting glucose: normal 3.9-5.5, prediabetes 5.6-6.9, diabetes >=7.0 mmol/L"
        },
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK430900/",
            "slug": "disease_hypertension_ckd",
            "chunk_type": "DISEASE",
            "severity": "URGENT",
            "note": "Hypertension in CKD — blood pressure targets, RAAS blockade"
        },
    ],

    # -----------------------------------------------------------------------
    # 7. INTERNAL MEDICINE & HEMATOLOGY — CBC Blood Count
    #    Features: WBC, RBC, Hgb, Hct, MCV, MCH, MCHC, Plt, neutrophil, etc.
    # -----------------------------------------------------------------------
    "hematology_internal": [
        {
            "url": "https://www.merckmanuals.com/professional/hematology-and-oncology/approach-to-the-patient-with-anemia/overview-of-anemia",
            "slug": "dept_overview_hematology",
            "chunk_type": "DEPARTMENT",
            "severity": "ROUTINE",
            "note": "Merck Manual — Hematology overview and anemia classification"
        },
        # WBC components
        {
            "url": "https://labtestsonline.org.uk/tests/white-blood-cell-wbc-count",
            "slug": "lab_wbc_range",
            "chunk_type": "GUIDELINE",
            "severity": "URGENT",
            "note": "WBC normal 4.0-11.0 x10^9/L — leukocytosis vs leukopenia interpretation"
        },
        {
            "url": "https://labtestsonline.org.uk/tests/neutrophils",
            "slug": "lab_neutrophil_range",
            "chunk_type": "GUIDELINE",
            "severity": "URGENT",
            "note": "Neutrophils 1.8-7.5 x10^9/L — neutrophilia in bacterial infection"
        },
        {
            "url": "https://labtestsonline.org.uk/tests/lymphocytes",
            "slug": "lab_lymphocyte_range",
            "chunk_type": "GUIDELINE",
            "severity": "ROUTINE",
            "note": "Lymphocytes 1.0-4.0 x10^9/L — lymphocytosis in viral infection"
        },
        # RBC components
        {
            "url": "https://labtestsonline.org.uk/tests/red-blood-cell-rbc-count",
            "slug": "lab_rbc_range",
            "chunk_type": "GUIDELINE",
            "severity": "URGENT",
            "note": "RBC normal male 4.7-6.1, female 4.2-5.4 x10^12/L"
        },
        {
            "url": "https://labtestsonline.org.uk/tests/haemoglobin",
            "slug": "lab_hemoglobin_range",
            "chunk_type": "GUIDELINE",
            "severity": "URGENT",
            "note": "Hemoglobin: male 130-170, female 120-150 g/L — anemia grading WHO"
        },
        {
            "url": "https://labtestsonline.org.uk/tests/mcv",
            "slug": "lab_mcv_range",
            "chunk_type": "GUIDELINE",
            "severity": "ROUTINE",
            "note": "MCV 80-100 fL — microcytic vs normocytic vs macrocytic anemia"
        },
        {
            "url": "https://labtestsonline.org.uk/tests/platelet-count",
            "slug": "lab_platelet_range",
            "chunk_type": "GUIDELINE",
            "severity": "URGENT",
            "note": "Platelets 150-400 x10^9/L — thrombocytopenia vs thrombocytosis"
        },
        # Diseases
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK448065/",
            "slug": "disease_iron_deficiency_anemia",
            "chunk_type": "DISEASE",
            "severity": "URGENT",
            "note": "StatPearls — Iron deficiency anemia: low MCV, low ferritin, CBC pattern"
        },
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK507832/",
            "slug": "disease_bacterial_infection_cbc",
            "chunk_type": "DISEASE",
            "severity": "URGENT",
            "note": "StatPearls — Bacterial infection CBC: elevated WBC, neutrophilia, left shift"
        },
        {
            "url": "https://www.ncbi.nlm.nih.gov/books/NBK560705/",
            "slug": "disease_leukemia_cbc_pattern",
            "chunk_type": "DISEASE",
            "severity": "EMERGENCY",
            "note": "StatPearls — Leukemia CBC pattern: extreme leukocytosis, blast cells"
        },
        {
            "url": "https://labtestsonline.org.uk/conditions/full-blood-count",
            "slug": "cbc_interpretation_guide",
            "chunk_type": "GUIDELINE",
            "severity": "ROUTINE",
            "note": "Full blood count interpretation — complete guide to all CBC components"
        },
    ],
}

# ---------------------------------------------------------------------------
# Core fetch logic
# ---------------------------------------------------------------------------

def setup_directories(departments):
    """Create output directory structure."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for dept in departments:
        os.makedirs(os.path.join(OUTPUT_DIR, dept), exist_ok=True)
    print(f"📁 Output directory: {OUTPUT_DIR}/")


def build_frontmatter(entry: dict, dept: str, url: str) -> str:
    """Build YAML-style frontmatter for each document — used as RAG metadata."""
    return f"""---
source_url: {url}
department: {dept}
chunk_type: {entry.get('chunk_type', 'GUIDELINE')}
severity: {entry.get('severity', 'ROUTINE')}
slug: {entry.get('slug', 'unknown')}
note: {entry.get('note', '')}
fetched_at: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}
---

"""


def fetch_url(url: str, retries: int = MAX_RETRIES) -> str | None:
    """Fetch URL content via Jina Reader API with retry logic."""
    jina_url = f"{JINA_BASE}{url}"
    headers = {
        "Accept": "text/markdown",
        "Authorization": f"Bearer {JINA_API_KEY}"
    }
    for attempt in range(1, retries + 2):
        try:
            response = requests.get(
                jina_url,
                timeout=REQUEST_TIMEOUT,
                headers=headers,
            )
            if response.status_code == 200:
                return response.text
            else:
                print(f"     ⚠️  HTTP {response.status_code} (attempt {attempt})")
        except requests.exceptions.Timeout:
            print(f"     ⚠️  Timeout (attempt {attempt})")
        except requests.exceptions.RequestException as exc:
            print(f"     ⚠️  Request error: {exc} (attempt {attempt})")

        if attempt <= retries:
            time.sleep(3)  # wait longer before retry

    return None


def save_document(content: str, dept: str, slug: str) -> str:
    """Save fetched markdown content to file."""
    file_path = os.path.join(OUTPUT_DIR, dept, f"{slug}.md")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    return file_path


def fetch_department(dept: str, entries: list, dry_run: bool = False) -> dict:
    """Fetch all URLs for a single department."""
    stats = {"success": 0, "failed": 0, "skipped": 0}

    print(f"\n{'='*60}")
    print(f"  Department: {dept.upper().replace('_', ' ')}")
    print(f"  Articles: {len(entries)}")
    print(f"{'='*60}")

    for i, entry in enumerate(entries, 1):
        url = entry["url"]
        slug = entry["slug"]
        note = entry.get("note", "")
        file_path = os.path.join(OUTPUT_DIR, dept, f"{slug}.md")

        print(f"\n  [{i}/{len(entries)}] {slug}")
        print(f"  URL: {url}")
        print(f"  Note: {note}")

        # Skip if already fetched (resumable pipeline)
        if os.path.exists(file_path):
            print("Already exists — skipping")
            stats["skipped"] += 1
            continue

        if dry_run:
            print(f"  [DRY RUN] Would fetch → {file_path}")
            stats["success"] += 1
            continue

        content = fetch_url(url)

        if content:
            frontmatter = build_frontmatter(entry, dept, url)
            full_content = frontmatter + content
            saved_path = save_document(full_content, dept, slug)
            print(f"  ✅ Saved: {saved_path} ({len(content):,} chars)")
            stats["success"] += 1
        else:
            print(f"  ❌ Failed after {MAX_RETRIES + 1} attempts")
            stats["failed"] += 1

        # Respect rate limits
        time.sleep(SLEEP_BETWEEN_REQUESTS)

    return stats


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="HealthAI — Medical Knowledge Base Ingestion Pipeline"
    )
    parser.add_argument(
        "--dept",
        type=str,
        default=None,
        help="Fetch specific department only (e.g. --dept respiratory)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print URLs without fetching",
    )
    args = parser.parse_args()

    # Filter departments if specified
    if args.dept:
        if args.dept not in KNOWLEDGE_BASE:
            print(f"❌ Unknown department: {args.dept}")
            print(f"   Available: {', '.join(KNOWLEDGE_BASE.keys())}")
            return
        target = {args.dept: KNOWLEDGE_BASE[args.dept]}
    else:
        target = KNOWLEDGE_BASE

    # Summary
    total_articles = sum(len(v) for v in target.values())
    estimated_minutes = (total_articles * (SLEEP_BETWEEN_REQUESTS + 5)) / 60

    print("\n" + "="*60)
    print("  HealthAI Medical Knowledge Base — Ingestion Pipeline")
    print("="*60)
    print(f"  Departments  : {len(target)}")
    print(f"  Total articles: {total_articles}")
    print(f"  Est. duration: ~{estimated_minutes:.0f} minutes")
    print(f"  Output dir   : {OUTPUT_DIR}/")
    if args.dry_run:
        print("  Mode         : DRY RUN")
    print("="*60)

    setup_directories(target.keys())

    # Run pipeline
    overall_stats = {"success": 0, "failed": 0, "skipped": 0}
    failed_urls = []

    for dept, entries in target.items():
        dept_stats = fetch_department(dept, entries, dry_run=args.dry_run)
        for key in overall_stats:
            overall_stats[key] += dept_stats[key]

        # Track failed for summary
        if dept_stats["failed"] > 0:
            failed_urls.append(dept)

    # Final report
    print("\n" + "="*60)
    print("  PIPELINE COMPLETE")
    print("="*60)
    print(f"  ✅ Success : {overall_stats['success']}")
    print(f"  ⏭️  Skipped : {overall_stats['skipped']} (already existed)")
    print(f"  ❌ Failed  : {overall_stats['failed']}")

    if failed_urls:
        print(f"\n  Departments with failures: {', '.join(failed_urls)}")
        print("  Tip: Re-run the script — it skips already-fetched files.")

    print(f"\n  Knowledge base ready at: ./{OUTPUT_DIR}/")
    print("  Next step: run chunker.py to split into RAG-ready chunks\n")


if __name__ == "__main__":
    main()