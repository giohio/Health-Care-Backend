"""Seed EMR Result DB — lab orders and lab results per doctor + per patient."""
import json
import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from .constants import SPECIALTIES
from .db_urls import _emr_db_url
from .doctors import DOCTORS
from .patients import PATIENTS

# ── Per-doctor EMR templates ─────────────────────────────────────────────────
# First 2 entries use completed appointments; extras (index 2+) are standalone
# lab orders (appointment_id = NULL) seeded directly from patient identity.

EMR_TEMPLATES: dict[str, list[dict]] = {
    "dr.nguyen.van.an@healthai.dev": [
        {
            "test_name": "Complete Blood Count with Differential",
            "test_type": "blood_panel",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "DOCTOR_REVIEW",
            "ai_draft":  json.dumps([
                {"name": "Hemoglobin",   "value": "14.2", "unit": "g/dL",    "flag": "normal", "reference_low": "13.5", "reference_high": "17.5"},
                {"name": "Hematocrit",   "value": "42.8", "unit": "%",        "flag": "normal", "reference_low": "41",   "reference_high": "53"},
                {"name": "WBC",          "value": "7.8",  "unit": "10^3/uL",  "flag": "normal", "reference_low": "4.5",  "reference_high": "11.0"},
                {"name": "Neutrophils",  "value": "58",   "unit": "%",        "flag": "normal", "reference_low": "50",   "reference_high": "70"},
                {"name": "Lymphocytes",  "value": "32",   "unit": "%",        "flag": "normal", "reference_low": "20",   "reference_high": "40"},
                {"name": "Platelets",    "value": "210",  "unit": "10^3/uL",  "flag": "normal", "reference_low": "150",  "reference_high": "400"},
                {"name": "MCV",          "value": "86",   "unit": "fL",       "flag": "normal", "reference_low": "80",   "reference_high": "100"},
            ]),
            "notes": (
                "AI Analysis: CBC is fully within normal limits. No cytopenias, leukocytosis, or thrombocytopenia detected. "
                "Hemoglobin 14.2 g/dL — adequate for a male patient. MCV 86 fL rules out microcytic or macrocytic process. "
                "Neutrophil/lymphocyte ratio (NLR = 1.8) is within normal range — no subclinical inflammatory signal. "
                "Doctor Assessment: Normal CBC confirmed. Continue current cardiovascular medication. "
                "Monitor CBC annually or sooner if symptoms develop."
            ),
            "pub_text": None,
        },
        {
            "test_name": "12-Lead ECG (Resting)",
            "test_type": "ecg",
            "priority":  "urgent",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"lead": "Rhythm",    "finding": "Normal sinus rhythm, rate 72 bpm, regular",                              "severity": "normal"},
                {"lead": "PR",        "finding": "PR interval 0.16s — normal AV conduction",                               "severity": "normal"},
                {"lead": "QRS",       "finding": "QRS 0.08s narrow, no bundle branch block",                               "severity": "normal"},
                {"lead": "QTc",       "finding": "QTc 428 ms — within normal limits",                                      "severity": "normal"},
                {"lead": "ST/T",      "finding": "No ST elevation, depression, or T-wave inversion in any lead",            "severity": "normal"},
                {"lead": "Axis",      "finding": "Normal axis (-30 to +90 deg)",                                            "severity": "normal"},
            ]),
            "notes": (
                "AI Analysis: Completely normal resting ECG. Normal sinus rhythm at 72 bpm. No ischemic changes, "
                "no conduction abnormalities, no chamber hypertrophy pattern. QTc within safe limits — no drug-induced "
                "QT prolongation risk. Axis and intervals all normal. "
                "Doctor Assessment: ECG confirmed normal. No acute cardiac event. Cleared for current treatment plan. "
                "Reassess ECG in 12 months or if symptoms (palpitations, chest pain, syncope) develop."
            ),
            "pub_text": (
                "ECG REPORT — Resting 12-Lead\n"
                "Rhythm: Normal sinus rhythm, rate 72 bpm, regular.\n"
                "Intervals: PR 0.16s, QRS 0.08s, QTc 428 ms — all within normal limits.\n"
                "ST-T segment: No ischaemic changes. No T-wave abnormalities.\n"
                "Axis: Normal. No bundle branch block or ventricular hypertrophy pattern.\n"
                "IMPRESSION: Normal resting ECG. No acute or chronic ischaemic changes identified. "
                "Continue current cardiovascular management."
            ),
        },
    ],
    "dr.tran.thi.bich@healthai.dev": [
        {
            "test_name": "Abdominal X-Ray (KUB — Kidney, Ureter, Bladder)",
            "test_type": "abdominal_xray",
            "priority":  "routine",
            "file_type": "file",
            "status":    "DOCTOR_REVIEW",
            "ai_draft":  json.dumps([
                {"finding": "Normal bowel gas pattern — no gaseous distension",         "severity": "normal"},
                {"finding": "No free intraperitoneal air (no pneumoperitoneum)",          "severity": "normal"},
                {"finding": "No radiopaque calcifications along renal/ureteric course",  "severity": "normal"},
                {"finding": "Psoas shadows bilaterally visible — no retroperitoneal mass","severity": "normal"},
                {"finding": "Vertebral column and visible bony pelvis unremarkable",      "severity": "normal"},
            ]),
            "notes": (
                "AI Analysis: Abdominal plain film (KUB) is unremarkable. No features of bowel obstruction "
                "(no dilated loops >3cm small bowel or >6cm large bowel). No radio-opaque renal or ureteric calculi. "
                "No pneumoperitoneum. Psoas outlines preserved — no retroperitoneal process. "
                "Note: KUB has limited sensitivity for soft-tissue pathology. If clinical suspicion persists, "
                "consider ultrasound abdomen or CT KUB. Doctor review required before filing."
            ),
            "pub_text": None,
        },
        {
            "test_name": "Complete Blood Count with Differential (Follow-up)",
            "test_type": "blood_panel",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"name": "Hemoglobin",   "value": "13.8", "unit": "g/dL",    "flag": "normal",  "reference_low": "12.0", "reference_high": "16.0"},
                {"name": "Hematocrit",   "value": "41.2", "unit": "%",       "flag": "normal",  "reference_low": "36",   "reference_high": "48"},
                {"name": "WBC",          "value": "7.2",  "unit": "10^3/uL", "flag": "normal",  "reference_low": "4.5",  "reference_high": "11.0"},
                {"name": "Neutrophils",  "value": "62",   "unit": "%",       "flag": "normal",  "reference_low": "50",   "reference_high": "70"},
                {"name": "Lymphocytes",  "value": "28",   "unit": "%",       "flag": "normal",  "reference_low": "20",   "reference_high": "40"},
                {"name": "Monocytes",    "value": "7",    "unit": "%",       "flag": "normal",  "reference_low": "2",    "reference_high": "10"},
                {"name": "Platelets",    "value": "250",  "unit": "10^3/uL", "flag": "normal",  "reference_low": "150",  "reference_high": "400"},
                {"name": "MCV",          "value": "88",   "unit": "fL",      "flag": "normal",  "reference_low": "80",   "reference_high": "100"},
                {"name": "CRP",          "value": "3.2",  "unit": "mg/L",    "flag": "normal",  "reference_low": "0",    "reference_high": "10"},
            ]),
            "notes": (
                "AI Analysis: CBC and CRP are normal. Hemoglobin 13.8 g/dL — mild decrease from previous (14.2) but within range. "
                "WBC differential normal with no eosinophilia or basophilia. CRP 3.2 mg/L — no systemic inflammation. "
                "NLR (neutrophil-lymphocyte ratio) = 2.2 — within acceptable range for general medicine patients. "
                "AI did not modify interpretation from prior CBC. "
                "Doctor Assessment: Confirmed normal CBC. Slight Hb decline may reflect dietary changes. "
                "Recommend dietary iron and folate assessment at next visit. No action required at this time."
            ),
            "pub_text": (
                "COMPLETE BLOOD COUNT — Follow-up Report\n"
                "All parameters within normal reference range. Hemoglobin 13.8 g/dL (stable). "
                "WBC 7.2 with normal differential. Platelets 250 (adequate). CRP 3.2 — no inflammation.\n"
                "IMPRESSION: Normal CBC. No haematological abnormality. Continue current management. "
                "Annual CBC review recommended."
            ),
        },
    ],
    "dr.le.minh.duc@healthai.dev": [
        {
            "test_name": "Brain MRI (Epilepsy Protocol — T1/T2/FLAIR/DWI)",
            "test_type": "imaging",
            "priority":  "urgent",
            "file_type": "manual",
            "status":    "DOCTOR_REVIEW",
            "ai_draft":  json.dumps([
                {"sequence": "T2/FLAIR",     "finding": "No periventricular or subcortical white matter signal abnormality", "region": "bilateral cerebral hemispheres", "severity": "normal"},
                {"sequence": "T1",           "finding": "Mild generalised cerebral volume loss — cortical thinning frontal lobes", "region": "frontal lobes", "severity": "mild"},
                {"sequence": "DWI/ADC",      "finding": "No restricted diffusion — no acute ischaemia",                     "region": "all territories", "severity": "normal"},
                {"sequence": "T2*",          "finding": "No haemosiderin deposits — no prior microhaemorrhage",             "region": "basal ganglia, cerebellum", "severity": "normal"},
                {"sequence": "Hippocampus",  "finding": "No hippocampal sclerosis or asymmetry",                           "region": "mesial temporal", "severity": "normal"},
                {"sequence": "Post-contrast","finding": "No abnormal enhancement",                                          "region": "entire brain", "severity": "normal"},
            ]),
            "notes": (
                "AI Analysis: Epilepsy-protocol MRI performed for ongoing seizure disorder. "
                "No epileptogenic lesion identified (no cortical dysplasia, no mesial temporal sclerosis, no focal FLAIR signal). "
                "Mild frontal cortical atrophy noted — likely age-related; not epileptogenic. "
                "AI recommendation: Correlate with EEG to characterize seizure type. If refractory, consider functional MRI. "
                "Doctor review required — confirm clinical correlation before finalising interpretation."
            ),
            "pub_text": None,
        },
        {
            "test_name": "Skull X-Ray — AP + Lateral Views",
            "test_type": "skull_xray",
            "priority":  "urgent",
            "file_type": "file",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"view": "AP",       "finding": "No fracture line or stellate lucency through calvarium",          "severity": "normal"},
                {"view": "Lateral",  "finding": "Sella turcica size and shape normal — no J-shaped or enlarged sella","severity": "normal"},
                {"view": "Lateral",  "finding": "Normal vascular grooves — no abnormal channel pattern",             "severity": "normal"},
                {"view": "Both",     "finding": "No intracranial calcifications (pineal gland midline)",              "severity": "normal"},
                {"view": "Both",     "finding": "Orbital roofs, nasal sinuses unremarkable",                          "severity": "normal"},
            ]),
            "notes": (
                "AI Analysis: Standard skull X-ray AP and lateral views reviewed. No acute fracture. "
                "Sella turcica normal — no pituitary expansion. Vascular grooves within expected pattern. "
                "Pineal gland not calcified (or midline if calcified). No inner table erosion. "
                "Limitation: Plain skull X-ray has low sensitivity for intracranial pathology — CT/MRI should be used for definitive neurological assessment. "
                "Doctor Assessment: Plain skull X-ray normal. Patient referred for MRI as definitive imaging. No immediate bony skull pathology."
            ),
            "pub_text": (
                "SKULL X-RAY REPORT — AP and Lateral Views\n"
                "No fracture, dislocation, or bony abnormality identified. Sella turcica normal dimensions. "
                "Vascular grooves within normal distribution. No abnormal intracranial calcifications.\n"
                "IMPRESSION: Normal skull radiograph. No acute traumatic or structural bony abnormality. "
                "CT or MRI recommended for comprehensive intracranial evaluation."
            ),
        },
    ],
    "dr.pham.hong.van@healthai.dev": [
        {
            "test_name": "Epicutaneous Patch Test (Extended European Series)",
            "test_type": "other",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "DOCTOR_REVIEW",
            "ai_draft":  json.dumps([
                {"allergen": "Nickel sulfate 5%",      "reaction": "positive", "grade": "2+", "reading": "D48h", "interpretation": "Allergic contact reaction"},
                {"allergen": "Latex (Hevea extract)",  "reaction": "positive", "grade": "3+", "reading": "D48h", "interpretation": "Strong allergic reaction — high sensitization"},
                {"allergen": "Cobalt chloride 1%",     "reaction": "positive", "grade": "1+", "reading": "D48h", "interpretation": "Weak positive — co-sensitization with nickel common"},
                {"allergen": "Fragrance mix I",        "reaction": "negative", "grade": "0",  "reading": "D48h", "interpretation": "Not sensitized"},
                {"allergen": "Balsam of Peru",         "reaction": "negative", "grade": "0",  "reading": "D48h", "interpretation": "Not sensitized"},
                {"allergen": "Thiuram mix",            "reaction": "negative", "grade": "0",  "reading": "D48h", "interpretation": "Not sensitized"},
                {"allergen": "Methylisothiazolinone",  "reaction": "negative", "grade": "0",  "reading": "D48h", "interpretation": "Not sensitized"},
            ]),
            "notes": (
                "AI Analysis: Extended epicutaneous patch test reveals significant contact sensitization. "
                "Latex 3+ (strong positive) — type IV delayed hypersensitivity confirmed. Latex allergy documented, all future procedures must be latex-free. "
                "Nickel 2+ and Cobalt 1+ — common co-sensitization pattern; advise avoidance of metal jewelry and belt buckles. "
                "Fragrance series negative — no perfume allergy. "
                "AI Recommendation: Patient should be provided with written allergen avoidance list. "
                "Consider referral to occupational health if workplace exposure is suspected. Doctor review required."
            ),
            "pub_text": None,
        },
        {
            "test_name": "Dermatoscopy (Total Body Mapping — 3 Lesions)",
            "test_type": "imaging",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"lesion": "Site 1 — Left forearm 8mm",  "dermoscopy": "Fissures and ridges pattern, milia-like cysts present", "diagnosis": "Seborrhoeic keratosis",   "malignancy_risk": "none"},
                {"lesion": "Site 2 — Upper back 5mm",   "dermoscopy": "Uniform brown pigment network, no atypical vessels",      "diagnosis": "Benign melanocytic naevus","malignancy_risk": "none"},
                {"lesion": "Site 3 — Right arm 6mm",    "dermoscopy": "Comma vessels, regular globular pattern",                 "diagnosis": "Dermatofibroma",           "malignancy_risk": "none"},
                {"overall": "No features of malignant melanoma (no atypical network, no regression structures, no blue-white veil)"},
            ]),
            "notes": (
                "AI Analysis: Three pigmented lesions assessed with digital dermatoscopy. "
                "Site 1: Classic seborrhoeic keratosis — fissures, ridges, and milia-like cysts. Benign. "
                "Site 2: Benign melanocytic naevus — uniform pigment network within 4.5mm, no atypical features (no asymmetry, no irregular borders, no multicolour). "
                "Site 3: Dermatofibroma — comma vessels, regular globular pattern, no regression. Benign. "
                "AI ABCDE analysis: All lesions score 0 — no malignant characteristics identified. "
                "Doctor Assessment: All three lesions confirmed benign on clinical and dermatoscopic grounds. No biopsy required. "
                "Total body photography baseline taken for future monitoring. Patient advised sun protection."
            ),
            "pub_text": (
                "DERMATOSCOPY REPORT — Total Body Skin Examination\n"
                "Three pigmented lesions examined:\n"
                " 1. Left forearm: Seborrhoeic keratosis — benign, no action required.\n"
                " 2. Upper back: Benign melanocytic naevus — stable, annual monitoring.\n"
                " 3. Right arm: Dermatofibroma — benign.\n"
                "No features of malignant melanoma across all lesions examined.\n"
                "IMPRESSION: Three benign cutaneous lesions confirmed. Recommend annual dermatoscopic review. "
                "Patient educated on self-examination technique and sun-protective behaviour."
            ),
        },
    ],
    "dr.vo.thanh.tung@healthai.dev": [
        {
            "test_name": "Comprehensive Liver Function Panel",
            "test_type": "blood_panel",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "DOCTOR_REVIEW",
            "ai_draft":  json.dumps([
                {"name": "ALT (SGPT)",       "value": "52",  "unit": "U/L",   "flag": "high",   "reference_low": "7",   "reference_high": "40"},
                {"name": "AST (SGOT)",       "value": "44",  "unit": "U/L",   "flag": "high",   "reference_low": "10",  "reference_high": "40"},
                {"name": "GGT",              "value": "68",  "unit": "U/L",   "flag": "high",   "reference_low": "9",   "reference_high": "48"},
                {"name": "ALP",              "value": "92",  "unit": "U/L",   "flag": "normal", "reference_low": "44",  "reference_high": "147"},
                {"name": "Bilirubin Total",  "value": "1.2", "unit": "mg/dL", "flag": "normal", "reference_low": "0",   "reference_high": "1.2"},
                {"name": "Bilirubin Direct", "value": "0.3", "unit": "mg/dL", "flag": "normal", "reference_low": "0",   "reference_high": "0.3"},
                {"name": "Albumin",          "value": "4.1", "unit": "g/dL",  "flag": "normal", "reference_low": "3.5", "reference_high": "5.0"},
                {"name": "Total Protein",    "value": "7.4", "unit": "g/dL",  "flag": "normal", "reference_low": "6.3", "reference_high": "8.2"},
                {"name": "INR",              "value": "1.0", "unit": "",       "flag": "normal", "reference_low": "0.8", "reference_high": "1.2"},
            ]),
            "notes": (
                "AI Analysis: Mildly elevated transaminases (ALT 52, AST 44) with elevated GGT (68). "
                "ALT/AST ratio 1.18 — hepatocellular pattern (not cholestatic). Elevated GGT alongside ALT elevation suggests "
                "possible fatty liver disease or alcohol-related injury. ALP normal — no cholestasis. "
                "Albumin and INR normal — hepatic synthetic function preserved. "
                "AI Recommendation: Screen for NAFLD (non-alcoholic fatty liver) with hepatic ultrasound. "
                "Exclude medication-induced hepatotoxicity (review current NSAID/statin use). "
                "Recheck LFTs in 6 weeks after lifestyle modification. Doctor review required."
            ),
            "pub_text": None,
        },
        {
            "test_name": "Fasting Lipid Profile + Non-HDL Cholesterol",
            "test_type": "blood_panel",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"name": "Total Cholesterol",       "value": "245", "unit": "mg/dL", "flag": "high",   "reference_low": "0",  "reference_high": "200"},
                {"name": "LDL-Cholesterol",         "value": "162", "unit": "mg/dL", "flag": "high",   "reference_low": "0",  "reference_high": "130"},
                {"name": "HDL-Cholesterol",         "value": "38",  "unit": "mg/dL", "flag": "low",    "reference_low": "40", "reference_high": "60"},
                {"name": "Non-HDL Cholesterol",     "value": "207", "unit": "mg/dL", "flag": "high",   "reference_low": "0",  "reference_high": "160"},
                {"name": "Triglycerides",           "value": "225", "unit": "mg/dL", "flag": "high",   "reference_low": "0",  "reference_high": "150"},
                {"name": "LDL/HDL Ratio",           "value": "4.3", "unit": "",       "flag": "high",   "reference_low": "0",  "reference_high": "3.5"},
                {"name": "TC/HDL Ratio",            "value": "6.4", "unit": "",       "flag": "high",   "reference_low": "0",  "reference_high": "5.0"},
            ]),
            "notes": (
                "AI Analysis: Mixed atherogenic dyslipidaemia pattern. LDL 162 mg/dL — significantly above target (<130 for low-risk, <100 for high-risk). "
                "Non-HDL cholesterol 207 mg/dL (target <160) — elevated atherogenic fraction. TC/HDL ratio 6.4 and LDL/HDL 4.3 both indicate "
                "elevated cardiovascular risk. Triglycerides 225 mg/dL — borderline high, suggesting insulin resistance or secondary dyslipidaemia. "
                "AI ASCVD risk assessment suggests high 10-year risk. Statin therapy strongly indicated. "
                "Doctor Assessment: Patient is an orthopaedic patient with sedentary lifestyle post-surgery — compounding dyslipidaemia risk. "
                "Initiated atorvastatin 20mg OD. Advised Mediterranean diet, increase physical activity as tolerated. "
                "Recheck lipids in 8 weeks."
            ),
            "pub_text": (
                "LIPID PROFILE REPORT — Fasting Sample\n"
                "Total Cholesterol: 245 mg/dL (HIGH — target <200)\n"
                "LDL: 162 mg/dL (HIGH — target <130)\n"
                "HDL: 38 mg/dL (LOW — target >40)\n"
                "Triglycerides: 225 mg/dL (HIGH — target <150)\n"
                "Non-HDL Cholesterol: 207 mg/dL (HIGH)\n"
                "TC/HDL Ratio: 6.4 (elevated cardiovascular risk)\n"
                "IMPRESSION: Mixed atherogenic dyslipidaemia. High ASCVD risk profile. "
                "Statin therapy initiated (Atorvastatin 20mg). Dietary counselling provided. "
                "Repeat lipids in 8 weeks to assess treatment response."
            ),
        },
    ],
    "dr.pham.thi.lan.huong@healthai.dev": [
        {
            "test_name": "Chest X-Ray — PA and Lateral Views (COPD Follow-up)",
            "test_type": "imaging",
            "priority":  "routine",
            "file_type": "file",
            "status":    "DOCTOR_REVIEW",
            "ai_draft":  json.dumps([
                {"view": "PA",       "finding": "Bilateral hyperinflation — increased AP diameter",                                "region": "bilateral",  "severity": "mild"},
                {"view": "Lateral", "finding": "Flattened hemidiaphragms bilaterally — consistent with air trapping",              "region": "bilateral",  "severity": "mild"},
                {"view": "PA",       "finding": "Increased retrosternal airspace (barrel chest configuration)",                    "region": "anterior",   "severity": "mild"},
                {"view": "PA",       "finding": "No focal consolidation or mass lesion",                                            "region": "all zones",  "severity": "normal"},
                {"view": "PA",       "finding": "No pleural effusion or pneumothorax",                                             "region": "pleural",    "severity": "normal"},
                {"view": "PA",       "finding": "Heart size normal (CTR <0.5)",                                                   "region": "cardiac",    "severity": "normal"},
                {"view": "PA",       "finding": "Prominent bronchovascular markings bilaterally — chronic changes",                "region": "perihilar",  "severity": "mild"},
            ]),
            "notes": (
                "AI Analysis: Chest X-ray shows features consistent with established COPD. "
                "Bilateral hyperinflation with flattened diaphragms and increased retrosternal air space — typical air-trapping pattern. "
                "No new focal consolidation — no acute pneumonia or exacerbation superimposed at this time. "
                "No pleural effusion or pneumothorax. Cardiac silhouette normal. "
                "Comparison with prior X-ray recommended (if available) to assess progression. "
                "AI Recommendation: Continue current COPD management. Consider HRCT chest if clinical deterioration noted. "
                "Doctor review required before reporting."
            ),
            "pub_text": None,
        },
        {
            "test_name": "Full Spirometry + DLCO + Post-Bronchodilator (COPD Staging)",
            "test_type": "other",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"name": "FEV1 (pre-BD)",   "value": "58",   "unit": "%predicted", "flag": "low",    "interpretation": "Moderate obstruction"},
                {"name": "FEV1 (post-BD)",  "value": "62",   "unit": "%predicted", "flag": "low",    "interpretation": "Minimal reversibility (<12%) — irreversible obstruction"},
                {"name": "FVC",             "value": "74",   "unit": "%predicted", "flag": "normal"},
                {"name": "FEV1/FVC",        "value": "0.62", "unit": "ratio",       "flag": "low",    "reference_low": "0.70"},
                {"name": "TLC",             "value": "118",  "unit": "%predicted", "flag": "high",   "interpretation": "Air trapping — hyperinflation"},
                {"name": "RV/TLC ratio",    "value": "0.52", "unit": "",            "flag": "high",   "interpretation": "Significant air trapping"},
                {"name": "DLCO",            "value": "52",   "unit": "%predicted", "flag": "low",    "interpretation": "Reduced diffusing capacity — emphysematous component"},
                {"name": "DLCO/VA (KCO)",   "value": "58",   "unit": "%predicted", "flag": "low",    "interpretation": "Confirms emphysema pattern"},
            ]),
            "notes": (
                "AI Analysis: Spirometry confirms COPD GOLD Stage II (FEV1 58% predicted, FEV1/FVC 0.62, post-BD <12% change). "
                "Irreversible airflow obstruction — no significant bronchodilator response. "
                "TLC 118% and RV/TLC 0.52 — significant static hyperinflation and air trapping. "
                "DLCO 52% and KCO 58% both reduced — emphysematous component confirmed (parenchymal destruction pattern). "
                "AI Assessment: GOLD II COPD with emphysema. Classify mMRC dyspnoea grade and exacerbation history to guide pharmacotherapy. "
                "Doctor Assessment: GOLD B (High symptoms, low exacerbation risk). Initiated LAMA + LABA dual bronchodilation. "
                "Pulmonary rehabilitation referral made. Annual spirometry planned."
            ),
            "pub_text": (
                "PULMONARY FUNCTION TESTS — Comprehensive Report\n"
                "FEV1: 58% predicted (moderate obstruction, GOLD Stage II)\n"
                "FEV1/FVC: 0.62 (below 0.70 threshold — obstructive pattern confirmed)\n"
                "Post-bronchodilator response: +4% — not significant (irreversible obstruction)\n"
                "DLCO: 52% predicted — reduced diffusing capacity suggesting emphysematous change\n"
                "Static lung volumes: TLC 118%, RV/TLC 0.52 — significant hyperinflation\n"
                "IMPRESSION: COPD GOLD Stage II with emphysema (irreversible obstruction + reduced DLCO). "
                "Dual LAMA/LABA bronchodilation initiated. Pulmonary rehabilitation referral placed. "
                "Consider HRCT chest to quantify emphysema distribution."
            ),
        },
    ],
    "dr.hoang.van.minh@healthai.dev": [
        {
            "test_name": "Comprehensive Kidney Function + Electrolytes",
            "test_type": "blood_panel",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "DOCTOR_REVIEW",
            "ai_draft":  json.dumps([
                {"name": "Creatinine",     "value": "2.1",  "unit": "mg/dL",  "flag": "high",  "reference_low": "0.6", "reference_high": "1.2"},
                {"name": "BUN",           "value": "38",   "unit": "mg/dL",  "flag": "high",  "reference_low": "7",   "reference_high": "25"},
                {"name": "BUN/Creatinine","value": "18.1", "unit": "ratio",  "flag": "normal","reference_low": "10",  "reference_high": "20"},
                {"name": "eGFR (CKD-EPI)","value": "32",   "unit": "mL/min", "flag": "low",   "reference_low": "60",  "reference_high": "120"},
                {"name": "Uric Acid",     "value": "8.2",  "unit": "mg/dL",  "flag": "high",  "reference_low": "3.5", "reference_high": "7.2"},
                {"name": "Potassium",     "value": "5.6",  "unit": "mEq/L",  "flag": "high",  "reference_low": "3.5", "reference_high": "5.1"},
                {"name": "Sodium",        "value": "138",  "unit": "mEq/L",  "flag": "normal"},
                {"name": "Bicarbonate",   "value": "19",   "unit": "mEq/L",  "flag": "low",   "reference_low": "22",  "reference_high": "29"},
                {"name": "Calcium",       "value": "8.8",  "unit": "mg/dL",  "flag": "normal"},
                {"name": "Phosphorus",    "value": "4.8",  "unit": "mg/dL",  "flag": "high",  "reference_low": "2.5", "reference_high": "4.5"},
            ]),
            "notes": (
                "AI Analysis: CKD Stage 3b confirmed (eGFR 32 mL/min). Electrolyte and metabolic complications present: "
                "Hyperkalemia K+ 5.6 mEq/L — risk of fatal arrhythmia above 6.0. Immediate dietary restriction of potassium "
                "(avoid bananas, oranges, tomatoes, potatoes). Consider sodium polystyrene sulfonate if dietary restriction insufficient. "
                "Metabolic acidosis (HCO3 19) — consider oral sodium bicarbonate 650mg TID. "
                "Hyperphosphatemia (4.8) — phosphate binder recommended with meals (calcium carbonate or sevelamer). "
                "Hyperuricaemia (8.2) — urate-lowering therapy (allopurinol — dose-adjusted for eGFR). "
                "BUN/Creatinine ratio 18.1 — intrinsic renal disease pattern (not pre-renal). "
                "Doctor review required before issuing recommendations."
            ),
            "pub_text": None,
        },
        {
            "test_name": "Urinalysis with Microscopy + Urine ACR",
            "test_type": "urine",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"test": "Dipstick",      "parameter": "Protein",    "value": "3+",         "flag": "high",   "interpretation": "Heavy proteinuria (approx >300 mg/dL)"},
                {"test": "Dipstick",      "parameter": "Blood",      "value": "2+",         "flag": "high",   "interpretation": "Haematuria"},
                {"test": "Dipstick",      "parameter": "Glucose",    "value": "negative",   "flag": "normal"},
                {"test": "Dipstick",      "parameter": "Nitrite",    "value": "negative",   "flag": "normal", "interpretation": "No bacterial UTI"},
                {"test": "Microscopy",    "parameter": "RBC casts",  "value": "2-4/lpf",   "flag": "high",   "interpretation": "PATHOGNOMONIC of glomerulonephritis"},
                {"test": "Microscopy",    "parameter": "WBC",        "value": "5-8/hpf",   "flag": "normal"},
                {"test": "Microscopy",    "parameter": "Granular casts","value": "1-2/lpf","flag": "high",   "interpretation": "Suggests renal tubular injury"},
                {"test": "Quantitative",  "parameter": "Urine ACR",  "value": "420",        "unit": "mg/g",  "flag": "high",   "reference_low": "0", "reference_high": "30", "interpretation": "Macroalbuminuria — nephrotic-range approaching"},
            ]),
            "notes": (
                "AI Analysis: Critical urinalysis findings — RBC casts present (pathognomonic for glomerulonephritis). "
                "Heavy proteinuria 3+ with urine ACR 420 mg/g (macroalbuminuria). Granular casts indicate concurrent tubular injury. "
                "Combined RBC casts + heavy proteinuria = nephritic-nephrotic overlap syndrome. Immediate nephrology evaluation required. "
                "Differential: IgA nephropathy (most common in this demographic), lupus nephritis (check ANA/complement), "
                "or anti-GBM disease (check anti-GBM antibody). "
                "Doctor Assessment: Nephrology referral made urgently. Renal biopsy planned within 1 week. "
                "Initiated oral prednisolone as bridge therapy pending biopsy result. ACE inhibitor dose maximised."
            ),
            "pub_text": (
                "URINALYSIS & MICROSCOPY REPORT\n"
                "Dipstick: Protein 3+, Blood 2+, Glucose negative, Nitrite negative.\n"
                "Microscopy: RBC casts 2-4/lpf (SIGNIFICANT — glomerulonephritis marker), Granular casts 1-2/lpf.\n"
                "Urine ACR: 420 mg/g — macroalbuminuria (nephrotic-range approaching).\n"
                "IMPRESSION: Findings highly consistent with active glomerulonephritis (nephritic-nephrotic overlap). "
                "RBC casts are pathognomonic. Urgent nephrology referral and renal biopsy arranged. "
                "ACE inhibitor therapy optimised. Immunosuppressive therapy under consideration."
            ),
        },
    ],
    "dr.nguyen.thi.hue.linh@healthai.dev": [
        {
            "test_name": "CBC with Differential + Iron Studies + Ferritin",
            "test_type": "blood_panel",
            "priority":  "urgent",
            "file_type": "manual",
            "status":    "DOCTOR_REVIEW",
            "ai_draft":  json.dumps([
                {"name": "Hemoglobin",       "value": "8.2",  "unit": "g/dL",    "flag": "low",   "reference_low": "12",  "reference_high": "16"},
                {"name": "MCV",              "value": "68",   "unit": "fL",      "flag": "low",   "reference_low": "80",  "reference_high": "100"},
                {"name": "MCH",              "value": "22",   "unit": "pg",      "flag": "low",   "reference_low": "26",  "reference_high": "34"},
                {"name": "MCHC",             "value": "28",   "unit": "g/dL",    "flag": "low",   "reference_low": "32",  "reference_high": "36"},
                {"name": "RDW",              "value": "18",   "unit": "%",       "flag": "high",  "reference_low": "11.5","reference_high": "14.5"},
                {"name": "WBC",              "value": "7.1",  "unit": "10^3/uL", "flag": "normal"},
                {"name": "Platelets",        "value": "320",  "unit": "10^3/uL", "flag": "normal","interpretation": "Reactive thrombocytosis — common in iron deficiency"},
                {"name": "Serum Iron",       "value": "22",   "unit": "ug/dL",   "flag": "low",   "reference_low": "60",  "reference_high": "170"},
                {"name": "TIBC",             "value": "465",  "unit": "ug/dL",   "flag": "high",  "reference_low": "240", "reference_high": "450"},
                {"name": "Transferrin Sat.", "value": "4.7",  "unit": "%",       "flag": "low",   "reference_low": "20",  "reference_high": "50"},
                {"name": "Ferritin",         "value": "6",    "unit": "ng/mL",   "flag": "low",   "reference_low": "12",  "reference_high": "150"},
            ]),
            "notes": (
                "AI Analysis: Severe microcytic hypochromic anaemia with profoundly depleted iron stores. "
                "All indices consistent with iron deficiency: MCV 68, MCH 22, MCHC 28, RDW elevated (anisocytosis). "
                "Iron stores critically low: ferritin 6 ng/mL, transferrin saturation 4.7%, TIBC elevated (iron-hungry state). "
                "Reactive thrombocytosis (platelets 320) — expected response to iron deficiency. "
                "AI Recommendation: Oral iron unlikely adequate for Hb 8.2 — recommend IV iron infusion (ferric carboxymaltose 1g). "
                "Investigate source of iron deficiency: menorrhagia (gynaecology referral), GI blood loss (stool OB test, endoscopy). "
                "Doctor review required before initiating therapy."
            ),
            "pub_text": None,
        },
        {
            "test_name": "Peripheral Blood Film Morphology Review",
            "test_type": "blood_panel",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"cell_type": "Erythrocytes",  "morphology": "Microcytic, hypochromic; marked anisocytosis; pencil cells and target cells present",            "severity": "significant"},
                {"cell_type": "WBC",           "morphology": "Normal leucocyte morphology. No blast cells, no hypersegmented neutrophils, no atypical lymphocytes","severity": "normal"},
                {"cell_type": "Platelets",     "morphology": "Platelets adequate in number, normal morphology. No platelet clumping.",                            "severity": "normal"},
                {"overall": "Pattern consistent with iron deficiency anaemia. No haemolysis markers (no spherocytes, no polychromasia). No myeloproliferative features."},
            ]),
            "notes": (
                "AI Analysis: Peripheral blood film confirms iron deficiency anaemia pattern. "
                "Microcytic, hypochromic RBCs with pencil cells (elongated red cells) and target cells — classic IDA morphology. "
                "Marked anisocytosis (size variation) consistent with iron-limited erythropoiesis. "
                "No spherocytes — autoimmune haemolytic anaemia excluded. No polychromasia — no haemolytic compensation. "
                "WBC line normal — no dysplastic features to suggest MDS. No blasts — myeloid malignancy not supported. "
                "Doctor Assessment: Blood film confirms iron deficiency. IDA confirmed. "
                "IV iron (Ferinject 1000mg) administered. GI blood loss investigation ordered (stool OB positive — referred for colonoscopy)."
            ),
            "pub_text": (
                "PERIPHERAL BLOOD FILM REPORT\n"
                "Red cells: Microcytic, hypochromic with pencil cells and target cells. Marked anisocytosis. Consistent with iron deficiency anaemia.\n"
                "White cells: Normal morphology throughout all series. No blasts, no hypersegmentation, no atypical cells.\n"
                "Platelets: Adequate in number and morphology. No platelet clumping.\n"
                "IMPRESSION: Morphology consistent with iron deficiency anaemia. No haemolytic, megaloblastic, or haematological malignancy features. "
                "IV iron therapy administered. GI source investigation arranged (colonoscopy for occult blood loss)."
            ),
        },
    ],
    "dr.tran.van.phuong@healthai.dev": [
        {
            "test_name": "Abdominal X-Ray (KUB) + Soft Tissue Assessment",
            "test_type": "abdominal_xray",
            "priority":  "routine",
            "file_type": "file",
            "status":    "DOCTOR_REVIEW",
            "ai_draft":  json.dumps([
                {"region": "Small bowel",      "finding": "Normal gas pattern — no dilated loops (>3 cm threshold)",              "severity": "normal"},
                {"region": "Large bowel",      "finding": "Normal haustra pattern — no distension (>6 cm threshold)",             "severity": "normal"},
                {"region": "Retroperitoneum",  "finding": "No radiopaque calcifications along renal or ureteric course",          "severity": "normal"},
                {"region": "Bladder",          "finding": "Bladder outline not clearly delineated on plain film",                  "severity": "normal"},
                {"region": "Bony pelvis",      "finding": "No lytic or sclerotic lesions. No hip joint pathology visible.",        "severity": "normal"},
                {"region": "Vertebrae",        "finding": "L1-L5 and visible thoracic vertebrae show mild degenerative changes",   "severity": "mild"},
            ]),
            "notes": (
                "AI Analysis: Abdominal plain film (KUB) is largely unremarkable. No bowel obstruction pattern, no free gas. "
                "No radiopaque renal calculi along known renal/ureteric course — however KUB has only ~60% sensitivity for uric acid stones (radiolucent). "
                "Mild lumbar degenerative changes visible — incidental finding in this endocrinology patient. "
                "AI Recommendation: If renal stone disease is clinically suspected, CT KUB non-contrast is preferred. "
                "Doctor review required."
            ),
            "pub_text": None,
        },
        {
            "test_name": "Thyroid Function Panel + Autoantibodies",
            "test_type": "blood_panel",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"name": "TSH",       "value": "0.04", "unit": "mIU/L", "flag": "low",   "reference_low": "0.4",  "reference_high": "4.0"},
                {"name": "Free T4",   "value": "4.2",  "unit": "ng/dL",  "flag": "high",  "reference_low": "0.8",  "reference_high": "1.8"},
                {"name": "Free T3",   "value": "9.8",  "unit": "pg/mL",  "flag": "high",  "reference_low": "2.3",  "reference_high": "4.2"},
                {"name": "Total T4",  "value": "18.4", "unit": "ug/dL",  "flag": "high",  "reference_low": "4.5",  "reference_high": "12.5"},
                {"name": "TRAb",      "value": "6.8",  "unit": "IU/L",   "flag": "high",  "reference_low": "0",    "reference_high": "1.75"},
                {"name": "Anti-TPO",  "value": "220",  "unit": "IU/mL",  "flag": "high",  "reference_low": "0",    "reference_high": "35"},
                {"name": "Anti-Tg",   "value": "85",   "unit": "IU/mL",  "flag": "high",  "reference_low": "0",    "reference_high": "60"},
            ]),
            "notes": (
                "AI Analysis: Overt hyperthyroidism pattern — profoundly suppressed TSH (0.04) with markedly elevated FT4 (4.2) and FT3 (9.8). "
                "TRAb strongly positive (6.8 IU/L) — confirms Graves' disease autoimmune aetiology (TSH receptor stimulating antibodies). "
                "Anti-TPO and Anti-Tg both elevated — consistent with autoimmune thyroid disease. "
                "Clinical risk: high FT3 increases risk of thyroid storm and AF. Check ECG and consider beta-blockade. "
                "AI Recommendation: Initiate anti-thyroid therapy (carbimazole 20-30mg/day). Refer to ophthalmology for Graves' orbitopathy screening. "
                "Doctor Assessment: Graves' disease confirmed. Carbimazole 30mg OD started. Propranolol 40mg BD for symptom control. "
                "Ophthalmology referral placed. Repeat TFT in 6 weeks."
            ),
            "pub_text": (
                "THYROID FUNCTION TEST REPORT\n"
                "TSH: 0.04 mIU/L (SUPPRESSED)\n"
                "Free T4: 4.2 ng/dL (HIGH — 2.3x upper limit)\n"
                "Free T3: 9.8 pg/mL (HIGH — 2.3x upper limit)\n"
                "TRAb: 6.8 IU/L (POSITIVE — Graves antibody confirmed)\n"
                "Anti-TPO: 220 IU/mL (Positive — autoimmune thyroid disease)\n"
                "IMPRESSION: Graves' disease with overt hyperthyroidism. TRAb positive confirms autoimmune aetiology. "
                "Carbimazole 30mg OD initiated. Propranolol for symptom control. "
                "Ophthalmology referral for Graves' orbitopathy screening. Repeat TFT in 6 weeks."
            ),
        },
    ],
}

# ── Per-patient standalone lab templates (no appointment required) ─────────────
# Keyed by patient email. Each entry is an independent lab order for that patient.
# doctor_email is the patient's primary doctor (from PATIENTS list).

PATIENT_LAB_TEMPLATES: dict[str, list[dict]] = {
    # ── Cardiology patients ─────────────────────────────────────────────────
    "patient.le.thi.mai@healthai.dev": [
        {
            "test_name": "HbA1c & Fasting Glucose",
            "test_type": "blood_panel",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"name": "HbA1c",         "value": "5.4", "unit": "%",      "flag": "normal", "reference_low": "0",   "reference_high": "5.7"},
                {"name": "Fasting Glucose","value": "92",  "unit": "mg/dL",  "flag": "normal", "reference_low": "70",  "reference_high": "100"},
            ]),
            "notes": (
                "AI Analysis: HbA1c 5.4% — well within non-diabetic range (<5.7%). Fasting glucose 92 mg/dL — euglycaemic. "
                "No trend toward insulin resistance. HOMA-IR within normal range based on fasting glucose. "
                "Doctor Assessment: Glucose metabolism fully normal in this cardiovascular patient. No pre-diabetes or metabolic syndrome component. "
                "Continue current dietary habits. Annual HbA1c monitoring recommended given hypertension co-morbidity."
            ),
            "pub_text": (
                "GLYCAEMIC ASSESSMENT REPORT\n"
                "HbA1c: 5.4% (Normal — target <5.7%)\n"
                "Fasting Glucose: 92 mg/dL (Normal — target 70-100)\n"
                "IMPRESSION: No evidence of diabetes or pre-diabetes. Glucose metabolism within optimal range. "
                "Annual monitoring recommended in context of cardiovascular risk management."
            ),
        },
        {
            "test_name": "24-hour Ambulatory Blood Pressure Monitoring",
            "test_type": "ecg",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"name": "Daytime mean SBP", "value": "138", "unit": "mmHg", "flag": "high",   "reference_low": "0",  "reference_high": "135"},
                {"name": "Daytime mean DBP", "value": "86",  "unit": "mmHg", "flag": "high",   "reference_low": "0",  "reference_high": "85"},
                {"name": "Nighttime dipping","value": "12",  "unit": "%",    "flag": "normal"},
            ]),
            "notes": (
                "AI Analysis: 24-hour ABPM shows daytime mean SBP 138/86 mmHg — borderline stage 1 hypertension (>135/85 daytime threshold). "
                "Nocturnal dipping 12% — adequate dipper pattern (normal >10%). No white-coat hypertension pattern. "
                "AI Recommendation: Current antihypertensive therapy partially effective. Consider dose upward titration or adding second agent. "
                "Doctor Assessment: True ambulatory hypertension confirmed. "
                "Amlodipine dose increased from 5mg to 10mg OD. Repeat ABPM in 3 months. Target daytime SBP <130."
            ),
            "pub_text": (
                "24-HOUR AMBULATORY BLOOD PRESSURE MONITORING REPORT\n"
                "Daytime mean: 138/86 mmHg (HIGH — threshold 135/85)\n"
                "Nocturnal dipping: 12% — dipper pattern preserved (normal >10%)\n"
                "24h mean: 130/82 mmHg\n"
                "IMPRESSION: Borderline stage 1 ambulatory hypertension with preserved nocturnal dipping. "
                "True hypertension confirmed. Antihypertensive dose optimised. Repeat ABPM in 3 months."
            ),
        },
        {
            "test_name": "Lipid Profile",
            "test_type": "blood_panel",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "DOCTOR_REVIEW",
            "ai_draft":  json.dumps([
                {"name": "Total Cholesterol", "value": "198", "unit": "mg/dL", "flag": "normal", "reference_low": "0",  "reference_high": "200"},
                {"name": "LDL",               "value": "118", "unit": "mg/dL", "flag": "normal", "reference_low": "0",  "reference_high": "130"},
                {"name": "HDL",               "value": "52",  "unit": "mg/dL", "flag": "normal", "reference_low": "40", "reference_high": "60"},
                {"name": "Triglycerides",     "value": "140", "unit": "mg/dL", "flag": "normal", "reference_low": "0",  "reference_high": "150"},
            ]),
            "notes": (
                "AI Analysis: All lipid parameters within optimal range. Total cholesterol 198 mg/dL (below 200 target). "
                "LDL 118 mg/dL — below 130 mg/dL target; acceptable for this patient's risk category. "
                "HDL 52 mg/dL — cardioprotective (target >40). Triglycerides 140 mg/dL — within normal range. "
                "TC/HDL ratio 3.8 — acceptable cardiovascular risk. Non-HDL cholesterol estimated 146 mg/dL — below 160 target. "
                "Doctor Assessment: Satisfactory lipid profile. No pharmacological intervention needed. "
                "Reinforce dietary Mediterranean pattern. Repeat lipids annually."
            ),
            "pub_text": None,
        },
    ],
    "patient.tran.van.long@healthai.dev": [
        {
            "test_name": "HbA1c & Metabolic Panel",
            "test_type": "blood_panel",
            "priority":  "urgent",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"name": "HbA1c",         "value": "8.2",  "unit": "%",      "flag": "high",  "reference_low": "0",  "reference_high": "6.5"},
                {"name": "Fasting Glucose","value": "186",  "unit": "mg/dL",  "flag": "high",  "reference_low": "70", "reference_high": "100"},
                {"name": "eGFR",           "value": "68",   "unit": "mL/min", "flag": "normal","reference_low": "60", "reference_high": "120"},
                {"name": "Creatinine",     "value": "1.1",  "unit": "mg/dL",  "flag": "normal","reference_low": "0.6","reference_high": "1.2"},
            ]),
            "notes": (
                "AI Analysis: Suboptimal glycaemic control with HbA1c 8.2% (target <7.0% for most T2DM patients). "
                "Fasting glucose 186 mg/dL suggests significant basal hyperglycaemia — inadequate basal insulin coverage or metformin dose. "
                "eGFR 68 mL/min (CKD Stage G2) — kidney function mildly reduced. Metformin acceptable down to eGFR >30. "
                "AI Recommendation: Add GLP-1 receptor agonist (semaglutide or dulaglutide) for glycaemic benefit + cardiovascular protection. "
                "Doctor Assessment: Agreed with AI recommendation. Initiated semaglutide 0.5mg weekly injection. "
                "Dietary counselling reinforced. Quarterly HbA1c monitoring. Renal function review in 3 months."
            ),
            "pub_text": (
                "DIABETES MANAGEMENT REPORT — Glycaemic Review\n"
                "HbA1c: 8.2% (POOR CONTROL — target <7.0%)\n"
                "Fasting Glucose: 186 mg/dL (HIGH)\n"
                "eGFR: 68 mL/min (Mildly reduced — CKD G2)\n"
                "IMPRESSION: Suboptimal glycaemic control. Renal function mildly impaired but metformin-safe. "
                "GLP-1 agonist (semaglutide) initiated for intensification. Target HbA1c <7.5% within 6 months. "
                "Quarterly review planned."
            ),
        },
        {
            "test_name": "Urine Microalbumin/Creatinine Ratio",
            "test_type": "urine",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"name": "Urine Albumin",         "value": "45",   "unit": "mg/L",    "flag": "high",  "reference_low": "0", "reference_high": "20"},
                {"name": "Urine Creatinine",       "value": "92",   "unit": "mg/dL",   "flag": "normal"},
                {"name": "Albumin/Creatinine Ratio","value": "48.9","unit": "mg/g",    "flag": "high",  "reference_low": "0", "reference_high": "30"},
            ]),
            "notes": (
                "AI Analysis: Urine ACR 48.9 mg/g — microalbuminuria range (30-300 mg/g). This is the earliest detectable marker of diabetic nephropathy. "
                "Urine albumin 45 mg/L — above normal threshold (>20 mg/L). Urine creatinine concentration normal — specimen adequately concentrated. "
                "Microalbuminuria in T2DM patient with poor HbA1c (8.2%) indicates progressive diabetic kidney disease (DKD). "
                "AI Risk Assessment: Without intervention, patient has >40% risk of progressing to overt proteinuria within 10 years. "
                "AI Recommendation: Maximise ACE inhibitor/ARB therapy (renoprotective). Optimise glycaemia (HbA1c <7%). Control BP <130/80. "
                "Doctor Assessment: Ramipril 5mg OD initiated for DKD protection. "
                "Glycaemia optimisation ongoing with semaglutide. Target BP adjusted to <130/80."
            ),
            "pub_text": (
                "URINE MICROALBUMIN/CREATININE REPORT\n"
                "Urine Albumin: 45 mg/L (HIGH — normal <20)\n"
                "Urine ACR: 48.9 mg/g (Microalbuminuria — range 30-300 mg/g)\n"
                "IMPRESSION: Microalbuminuria — earliest stage of diabetic nephropathy (DKD Stage 1). "
                "ACE inhibitor therapy (Ramipril) initiated for renoprotection. "
                "Glycaemic and blood pressure targets tightened. Repeat ACR in 3 months."
            ),
        },
        {
            "test_name": "Cardiac Stress Test (Exercise ECG)",
            "test_type": "ecg",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "DOCTOR_REVIEW",
            "ai_draft":  json.dumps([
                {"phase": "Rest",     "finding": "Normal sinus rhythm. No ST changes.", "heart_rate": "72 bpm",  "bp": "138/88 mmHg"},
                {"phase": "Peak",     "finding": "Achieved 88% target HR. No ST depression.", "heart_rate": "152 bpm", "bp": "178/94 mmHg"},
                {"phase": "Recovery", "finding": "HR normalised within 3 min.", "heart_rate": "84 bpm",  "bp": "148/86 mmHg"},
            ]),
            "notes": (
                "AI Analysis: Exercise stress test completed to 88% of maximum predicted heart rate (MPHR). "
                "No chest pain, dyspnoea, or significant arrhythmia during exercise or recovery. "
                "No ST segment changes in any lead throughout all exercise stages (>1mm depression would indicate ischaemia). "
                "BP response appropriate: systolic rise from 138 to 178 mmHg — normal hypertensive response. "
                "Heart rate recovery within 3 minutes — good autonomic function. Adequate METs for age. "
                "AI Assessment: Negative stress test — no inducible ischaemia at near-maximum exercise. Low immediate CAD risk. "
                "Doctor Assessment: Reassuring in this diabetic patient. No coronary revascularisation indicated. "
                "Continue current cardioprotective regimen. Repeat stress test in 2-3 years if asymptomatic."
            ),
            "pub_text": None,
        },
    ],
    "patient.vo.thi.hoa@healthai.dev": [
        {
            "test_name": "Complete Blood Count",
            "test_type": "blood_panel",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"name": "Hemoglobin", "value": "12.4", "unit": "g/dL",   "flag": "low",   "reference_low": "12.0", "reference_high": "16.0"},
                {"name": "WBC",        "value": "6.5",  "unit": "10³/μL", "flag": "normal"},
                {"name": "Platelets",  "value": "230",  "unit": "10³/μL", "flag": "normal"},
                {"name": "MCV",        "value": "82",   "unit": "fL",     "flag": "normal"},
            ]),
            "notes": (
                "AI Analysis: Hemoglobin 12.4 g/dL — borderline low (normal female 12.0-16.0 g/dL). MCV 82 fL — normocytic — suggests anaemia of chronic disease (ACD) "
                "rather than iron deficiency (which would show microcytosis MCV <80). WBC and platelets normal — no pancytopenia. "
                "AI Differential: In a cardiovascular patient, mild normocytic anaemia may reflect ACD from chronic inflammation, or early iron/B12 deficiency. "
                "AI Recommendation: Complete workup with iron studies (ferritin, TIBC) and vitamin B12/folate. "
                "Doctor Assessment: Borderline anaemia in context of cardiovascular disease — even mild anaemia increases cardiac workload. "
                "Iron studies ordered. Vitamin B12 checked. Dietary supplementation started. Repeat CBC in 6 weeks."
            ),
            "pub_text": (
                "COMPLETE BLOOD COUNT REPORT\n"
                "Hemoglobin: 12.4 g/dL (Borderline low — normal 12.0-16.0)\n"
                "MCV: 82 fL (Normocytic — ACD pattern)\n"
                "WBC: 6.5, Platelets: 230 — both normal.\n"
                "IMPRESSION: Mild normocytic anaemia — likely anaemia of chronic disease in context of cardiovascular comorbidity. "
                "Iron studies and vitamin B12 ordered. Dietary supplementation initiated. Repeat CBC in 6 weeks."
            ),
        },
        {
            "test_name": "Allergy Panel (IgE specific)",
            "test_type": "other",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"allergen": "Penicillin",    "IgE": "high",   "grade": "3+", "notes": "Confirmed allergy"},
                {"allergen": "Amoxicillin",   "IgE": "high",   "grade": "2+", "notes": "Cross-reactive"},
                {"allergen": "Cephalosporins","IgE": "low",    "grade": "0",  "notes": "Low cross-reactivity risk"},
                {"allergen": "House dust mite","IgE": "normal","grade": "0",  "notes": "Not sensitized"},
            ]),
            "notes": (
                "AI Analysis: Specific IgE testing confirms type I (IgE-mediated) penicillin hypersensitivity (grade 3+) and amoxicillin cross-reactivity (grade 2+). "
                "Structural basis: amoxicillin shares the beta-lactam ring with penicillin — cross-reaction expected in ~10-30% of penicillin-allergic patients. "
                "Cephalosporins: IgE grade 0 — low cross-reactivity risk (~1-2%) in this patient. "
                "AI Recommendation: Penicillin and amoxicillin strictly contraindicated — anaphylaxis risk. "
                "Cephalosporins may be used with supervised first-dose challenge if clinically necessary. "
                "Doctor Assessment: Written allergy record updated. Patient provided with allergen avoidance card and EpiPen prescription. "
                "MedAlert bracelet recommended."
            ),
            "pub_text": (
                "DRUG ALLERGY INVESTIGATION REPORT\n"
                "Penicillin G: IgE Class 3+ — Confirmed allergy (type I hypersensitivity)\n"
                "Amoxicillin: IgE Class 2+ — Cross-reactive (avoid)\n"
                "Cephalosporins: IgE Class 0 — Low cross-reactivity risk (use with supervision)\n"
                "House dust mite, Latex: Negative\n"
                "IMPRESSION: Confirmed IgE-mediated penicillin and amoxicillin allergy. Penicillin-class antibiotics CONTRAINDICATED. "
                "Allergy flagged in medical record. EpiPen prescribed. Cephalosporins permissible with supervised challenge."
            ),
        },
    ],
    # ── General Medicine patients (Dr. Tran Thi Bich) ─────────────────────
    "patient.nguyen.van.minh@healthai.dev": [
        {
            "test_name": "Chest X-Ray (AP)",
            "test_type": "imaging",
            "priority":  "routine",
            "file_type": "file",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"finding": "Increased peribronchial markings", "region": "bilateral lower lobes", "severity": "mild"},
                {"finding": "No consolidation or pleural effusion",                                 "severity": "normal"},
                {"finding": "Heart size normal",                                                    "severity": "normal"},
            ]),
            "notes": (
                "AI Analysis: Chest X-ray shows mild peribronchial cuffing bilaterally — circumferential thickening of bronchial walls, a recognized X-ray feature of asthma. "
                "No alveolar consolidation (no pneumonia, no aspiration). No pleural effusion. Lung volumes subjectively increased — air trapping component. "
                "Heart size normal (CTR <0.5). No mediastinal widening. "
                "Limitation: Chest X-ray is insensitive for mild asthma — normal CXR does NOT exclude asthma; this is a supportive finding only. "
                "Doctor Assessment: Mild peribronchial markings consistent with asthmatic airway inflammation. No acute infection. "
                "SABA inhaler continued; consider adding ICS if symptoms uncontrolled at next review."
            ),
            "pub_text": (
                "CHEST X-RAY REPORT — PA View\n"
                "Lung fields: Clear. No consolidation, mass, or pleural effusion.\n"
                "Airways: Mild peribronchial cuffing bilaterally — bronchial wall thickening, consistent with chronic airway inflammation.\n"
                "Heart: Normal cardiomegaly (CTR <0.5). No mediastinal lymphadenopathy.\n"
                "IMPRESSION: Mild peribronchial changes consistent with asthmatic airway disease. No acute infectious or structural pathology. "
                "Spirometry recommended for functional assessment."
            ),
        },
        {
            "test_name": "Pulmonary Function Test (Spirometry)",
            "test_type": "other",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"name": "FEV1",     "value": "72", "unit": "%predicted", "flag": "low"},
                {"name": "FVC",      "value": "85", "unit": "%predicted", "flag": "normal"},
                {"name": "FEV1/FVC", "value": "0.75","unit": "ratio",    "flag": "normal"},
            ]),
            "notes": (
                "AI Analysis: Pre-bronchodilator FEV1 72% predicted — mild obstruction (80-69% = mild by ERS criteria). "
                "Post-salbutamol: FEV1 84% predicted — improvement of 12 percentage points (>12% and >200mL = SIGNIFICANT reversibility). "
                "Significant reversibility confirms airway hyperresponsiveness — asthma diagnosis supported. FVC 85% and FEV1/FVC 0.75 within normal range. "
                "AI Assessment: Mild intermittent or mild persistent asthma (GINA Step 1-2). "
                "Doctor Assessment: Spirometry confirms asthma with good reversibility. Current SABA-only regimen appropriate for mild disease. "
                "If symptom frequency increases (>2/week), upgrade to ICS (budesonide 200mcg BD). "
                "Asthma action plan provided to patient."
            ),
            "pub_text": (
                "SPIROMETRY REPORT — Pre and Post Bronchodilator\n"
                "Pre-BD FEV1: 72% predicted (Mild obstruction)\n"
                "Post-BD FEV1: 84% predicted (improvement +12% — SIGNIFICANT reversibility)\n"
                "FVC: 85% predicted (normal)\n"
                "FEV1/FVC: 0.75 (normal)\n"
                "IMPRESSION: Mild reversible airflow obstruction — consistent with mild asthma. "
                "Significant bronchodilator response confirms asthma diagnosis. "
                "GINA Step 2 treatment escalation recommended if symptoms persist."
            ),
        },
    ],
    "patient.pham.thi.lan@healthai.dev": [
        {
            "test_name": "Complete Blood Count + CRP",
            "test_type": "blood_panel",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"name": "Hemoglobin", "value": "12.8", "unit": "g/dL",   "flag": "normal"},
                {"name": "WBC",        "value": "9.2",  "unit": "10³/μL", "flag": "high",  "reference_low": "4.5", "reference_high": "11.0"},
                {"name": "Neutrophils","value": "72",   "unit": "%",       "flag": "high",  "reference_low": "50",  "reference_high": "70"},
                {"name": "CRP",        "value": "18",   "unit": "mg/L",   "flag": "high",  "reference_low": "0",   "reference_high": "10"},
            ]),
            "notes": (
                "AI Analysis: Mild leukocytosis (WBC 9.2 — upper limit 11.0). Neutrophilia (72%) driving the leukocytosis — bacterial or early viral infection pattern. "
                "CRP 18 mg/L — mildly elevated (normal <10). CRP 18 suggests early-moderate inflammation, not severe sepsis (which typically >100 mg/L). "
                "Hemoglobin normal (12.8) — no anaemia. No significant cytopenias. "
                "AI Differential: Recent URTI, mild bacterial infection (pharyngitis, sinusitis), or early pneumonia. CXR was normal — pneumonia less likely. "
                "AI Recommendation: Repeat CBC and CRP in 2 weeks to confirm resolution. If CRP >50 or WBC >12 on repeat, investigate for focal bacterial infection. "
                "Doctor Assessment: Clinical impression of resolving URTI. No antibiotics prescribed (viral aetiology likely). "
                "Paracetamol for symptom control. Repeat bloods in 2 weeks."
            ),
            "pub_text": (
                "COMPLETE BLOOD COUNT + CRP REPORT\n"
                "WBC: 9.2 x10^3/uL (mildly elevated, neutrophilia 72%)\n"
                "Hemoglobin: 12.8 g/dL (normal)\n"
                "CRP: 18 mg/L (mildly elevated — normal <10)\n"
                "IMPRESSION: Mild neutrophilic leukocytosis with elevated CRP — consistent with acute inflammatory process (likely recent URTI or early infection). "
                "No antibiotic therapy initiated. Repeat CBC + CRP in 2 weeks to confirm resolution."
            ),
        },
    ],
    # ── Neurology patients (Dr. Le Minh Duc) ───────────────────────────────
    "patient.hoang.thi.thu@healthai.dev": [
        {
            "test_name": "Brain MRI with Contrast",
            "test_type": "imaging",
            "priority":  "urgent",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"finding": "No space-occupying lesions",               "region": "whole brain",    "severity": "normal"},
                {"finding": "Periventricular white matter changes",     "region": "frontal lobes",  "severity": "mild"},
                {"finding": "No restricted diffusion",                  "region": "DWI",            "severity": "normal"},
                {"finding": "Normal enhancement pattern",               "region": "post-contrast",  "severity": "normal"},
            ]),
            "notes": (
                "AI Analysis: Brain MRI with contrast reviewed. Key findings: mild periventricular white matter hyperintensities (WMH) on FLAIR in frontal lobes — "
                "Fazekas score Grade 1 (punctate foci, non-confluent). This pattern is seen in migraine with aura, hypertension, and normal ageing. "
                "No restricted diffusion (DWI/ADC normal) — acute ischaemic stroke excluded. No space-occupying lesion, no cortical infarcts. "
                "No pathological enhancement on post-contrast sequences — no active demyelination, no tumour, no abscess. "
                "AI Assessment: WMH pattern is non-specific but commonly associated with migraine with aura. "
                "AI Recommendation: Correlate with migraine frequency and vascular risk factors. Control BP to reduce WMH progression risk. "
                "Doctor Assessment: WMH consistent with long-standing migraine with aura. Patient reassured. "
                "No disease-modifying intervention required at this stage."
            ),
            "pub_text": (
                "BRAIN MRI REPORT — Standard Protocol with Contrast\n"
                "T2/FLAIR: Mild periventricular white matter hyperintensities, Fazekas Grade 1 (non-confluent) — frontal predominance.\n"
                "DWI/ADC: No restricted diffusion — acute ischaemia excluded.\n"
                "Post-contrast: No abnormal enhancement.\n"
                "Mass effect, midline shift: Absent.\n"
                "IMPRESSION: Non-specific mild periventricular WMH — Fazekas Grade 1. Commonly associated with migraine with aura or early microvascular change. "
                "No acute pathology. No malignancy or demyelination. "
                "Recommend optimising vascular risk factors to prevent WMH progression."
            ),
        },
        {
            "test_name": "EEG (Routine Wakefulness)",
            "test_type": "other",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "DOCTOR_REVIEW",
            "ai_draft":  json.dumps([
                {"finding": "Normal alpha rhythm 9–10 Hz posteriorly", "severity": "normal"},
                {"finding": "No epileptiform discharges",               "severity": "normal"},
                {"finding": "No focal slowing",                        "severity": "normal"},
            ]),
            "notes": (
                "AI Analysis: Routine wakefulness EEG reviewed. Background alpha rhythm well-formed at 9-10 Hz posteriorly — normal symmetric reactivity. "
                "No epileptiform discharges (no spikes, sharp waves, or spike-wave complexes) in any channel. No focal slowing. "
                "Photic stimulation: no photoparoxysmal response. No asymmetry in background rhythms. "
                "AI Assessment: Normal EEG. A normal EEG does not exclude epilepsy (sensitivity ~50% for single routine EEG). "
                "Migraine headache is supported as the diagnosis over epileptic seizures. "
                "Doctor Assessment: EEG normal — migraine diagnosis remains primary. No anti-epileptic therapy indicated. "
                "Migraine prophylaxis (propranolol 40mg BD) initiated. If unusual spells recur, repeat EEG with sleep deprivation."
            ),
            "pub_text": None,
        },
    ],
    "patient.bui.van.duc@healthai.dev": [
        {
            "test_name": "EEG (Sleep-deprived + Hyperventilation)",
            "test_type": "other",
            "priority":  "urgent",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"finding": "Generalized spike-and-wave discharges 3 Hz", "duration": "2.1 s", "severity": "significant"},
                {"finding": "Triggered by hyperventilation",               "severity": "significant"},
                {"finding": "Normal background rhythm inter-ictally",      "severity": "normal"},
            ]),
            "notes": (
                "AI Analysis: Sleep-deprived EEG with hyperventilation provocation. Significant findings: "
                "Generalized 3 Hz spike-and-wave discharges of 2.1-second duration triggered by hyperventilation — pathognomonic for idiopathic generalized epilepsy (IGE). "
                "Absence seizure phenotype (3 Hz classic pattern). Background rhythm normal inter-ictally. "
                "AI Assessment: Consistent with Juvenile Absence Epilepsy (JAE) or Childhood Absence Epilepsy (CAE) depending on age of onset. "
                "AI Recommendation: Valproate is first-line for IGE. Avoid triggers (hyperventilation, flickering lights, sleep deprivation). "
                "Doctor Assessment: IGE with absence seizure type confirmed. Valproate dose increased from 500mg BD to 750mg BD. "
                "Safety counselling given (driving, swimming, heights). Follow-up in 8 weeks with drug level monitoring."
            ),
            "pub_text": (
                "EEG REPORT — Sleep-Deprived Protocol with Provocation\n"
                "Background: Normal alpha rhythm inter-ictally.\n"
                "Epileptiform activity: Generalized 3 Hz spike-wave discharges, max duration 2.1s, triggered by hyperventilation.\n"
                "Ictal semiology: Consistent with absence seizure (brief behavioural arrest).\n"
                "IMPRESSION: Idiopathic Generalized Epilepsy — absence seizure type (3 Hz spike-wave pattern). "
                "Anti-epileptic therapy dose increased. Safety restrictions counselled. Repeat EEG in 3 months."
            ),
        },
        {
            "test_name": "Anti-Epileptic Drug Levels",
            "test_type": "blood_panel",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"name": "Valproate (Depakine)", "value": "62",  "unit": "μg/mL", "flag": "normal", "reference_low": "50", "reference_high": "100"},
                {"name": "Levetiracetam",        "value": "18",  "unit": "μg/mL", "flag": "normal", "reference_low": "12", "reference_high": "46"},
            ]),
            "notes": (
                "AI Analysis: Both anti-epileptic drug levels measured within therapeutic range. "
                "Valproate (Depakine): 62 mcg/mL — within target range 50-100 mcg/mL. Mid-range level confirms good compliance without toxicity risk. "
                "Levetiracetam: 18 mcg/mL — within therapeutic range 12-46 mcg/mL. Adequate drug exposure. "
                "No toxic range values (valproate toxicity risk above 150 mcg/mL, levetiracetam above 60 mcg/mL). "
                "AI Assessment: Dual-therapy AED levels confirm therapeutic compliance and adequate drug exposure. "
                "Doctor Assessment: Drug levels confirm patient compliance and therapeutic dosing. No dose adjustment needed currently. "
                "Monitor valproate level again at next visit after recent dose increase. Check LFTs (valproate hepatotoxicity monitoring)."
            ),
            "pub_text": (
                "ANTI-EPILEPTIC DRUG LEVEL REPORT\n"
                "Valproate (Depakine): 62 mcg/mL (Therapeutic — range 50-100)\n"
                "Levetiracetam: 18 mcg/mL (Therapeutic — range 12-46)\n"
                "IMPRESSION: Both AED levels therapeutic. No drug toxicity. Good compliance confirmed. "
                "No dose adjustment required at this time. Repeat valproate level post dose-increase at next visit."
            ),
        },
        {
            "test_name": "Liver Function Panel (Valproate monitoring)",
            "test_type": "blood_panel",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "DOCTOR_REVIEW",
            "ai_draft":  json.dumps([
                {"name": "ALT",             "value": "28",  "unit": "U/L",  "flag": "normal"},
                {"name": "AST",             "value": "25",  "unit": "U/L",  "flag": "normal"},
                {"name": "Ammonia",         "value": "38",  "unit": "μg/dL","flag": "normal", "reference_low": "15", "reference_high": "45"},
                {"name": "Platelet count",  "value": "220", "unit": "10³/μL","flag": "normal"},
            ]),
            "notes": (
                "AI Analysis: LFT panel as routine monitoring for valproate hepatotoxicity. "
                "ALT 28 and AST 25 both within normal limits (concern threshold: >3x ULN = >120 U/L). "
                "Serum ammonia 38 mcg/dL — within normal range (15-45). Valproate-induced hyperammonaemia excluded. "
                "Platelet count 220 — normal. Valproate can cause thrombocytopenia at high levels; not occurring here. "
                "AI Assessment: No evidence of valproate hepatotoxicity, hyperammonaemia, or thrombocytopenia. Safe to continue. "
                "AI Recommendation: Annual LFT + ammonia monitoring while on valproate. "
                "Doctor Assessment: LFTs and ammonia reassuringly normal. Valproate therapy safe to continue. "
                "Repeat LFTs in 6 months after recent dose increase to 750mg BD."
            ),
            "pub_text": None,
        },
    ],
    "patient.ly.thi.tuyet@healthai.dev": [
        {
            "test_name": "Brain CT Scan (Non-contrast)",
            "test_type": "imaging",
            "priority":  "urgent",
            "file_type": "file",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"finding": "No hemorrhage or midline shift", "severity": "normal"},
                {"finding": "No hyperdense lesion",          "severity": "normal"},
                {"finding": "Ventricles normal in size",     "severity": "normal"},
            ]),
            "notes": (
                "AI Analysis: Non-contrast brain CT reviewed as urgent imaging for severe headache. "
                "No acute intracranial haemorrhage (no hyperdense collections in subdural, epidural, or subarachnoid spaces). "
                "No midline shift. Ventricles normal in size and symmetry — no obstructive hydrocephalus. "
                "Cisterns patent at skull base — no uncal herniation. No hyperdense lesion suggestive of acute stroke. "
                "AI Assessment: CT normal. Catastrophic haemorrhage excluded. Note: CT has 98% sensitivity for SAH in first 6h but decreases after — LP if clinically suspected. "
                "Doctor Assessment: CT negative for haemorrhage. Clinical impression: chronic migraine with acute exacerbation. "
                "Lumbar puncture performed (xanthochromia negative) — SAH excluded. Migraine management optimised."
            ),
            "pub_text": (
                "BRAIN CT REPORT — Non-Contrast\n"
                "Parenchyma: No haemorrhage, no hypodense/hyperdense lesion.\n"
                "Ventricles: Normal size and configuration. No hydrocephalus.\n"
                "Cisterns: Patent. No midline shift.\n"
                "IMPRESSION: Normal brain CT. No acute intracranial pathology. "
                "Subarachnoid haemorrhage excluded on CT. Lumbar puncture performed — xanthochromia negative. "
                "Chronic migraine management optimised."
            ),
        },
    ],
    # ── Dermatology patients (Dr. Pham Hong Van) ───────────────────────────
    "patient.duong.van.khanh@healthai.dev": [
        {
            "test_name": "Skin Biopsy (Patch test site)",
            "test_type": "other",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"finding": "Spongiotic dermatitis consistent with eczema",  "severity": "moderate"},
                {"finding": "Lymphocytic infiltrate in dermis",              "severity": "moderate"},
                {"finding": "No malignant cells",                           "severity": "normal"},
            ]),
            "notes": (
                "AI Analysis: Skin biopsy from patch test site reviewed. "
                "Key features: spongiosis (intercellular oedema) with lymphocytic exocytosis into epidermis — classic for eczematous dermatitis. "
                "Lymphocytic infiltrate in papillary and reticular dermis (perivascular pattern). No eosinophils in significant numbers (excludes drug reaction pattern). "
                "No epidermal hyperplasia (excludes psoriasis). No malignant cells or lymphoma features. "
                "Combined with IgE panel (total IgE 420 IU/mL, nickel and latex sensitisation): "
                "AI Diagnosis: Chronic atopic dermatitis with exacerbation from contact allergens. "
                "AI Recommendation: Topical tacrolimus 0.1% for face/flexures; mometasone for trunk/limbs. Nickel and latex avoidance mandatory. "
                "Doctor Assessment: Histology confirms chronic atopic eczema. Dupilumab considered if inadequate response to topicals."
            ),
            "pub_text": (
                "DERMATOPATHOLOGY REPORT — Skin Biopsy\n"
                "Site: Patch test site (contact allergen site).\n"
                "Histology: Spongiotic dermatitis with lymphocytic exocytosis. Perivascular lymphocytic infiltrate in dermis. No eosinophils. No malignant cells.\n"
                "Diagnosis: Chronic eczematous (atopic) dermatitis.\n"
                "IMPRESSION: Histology consistent with atopic dermatitis. No malignancy or psoriasis. "
                "Topical immunomodulator therapy (tacrolimus) initiated. Allergen avoidance counselling provided (nickel, latex)."
            ),
        },
        {
            "test_name": "Total IgE + RAST Panel",
            "test_type": "other",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "DOCTOR_REVIEW",
            "ai_draft":  json.dumps([
                {"name": "Total IgE",    "value": "420", "unit": "IU/mL", "flag": "high",  "reference_low": "0", "reference_high": "100"},
                {"allergen": "Latex",    "IgE": "class 4 (very high)"},
                {"allergen": "Nickel",   "IgE": "class 3 (high)"},
                {"allergen": "Pollen",   "IgE": "class 1 (low)"},
            ]),
            "notes": (
                "AI Analysis: Total serum IgE 420 IU/mL — markedly elevated (normal <100 IU/mL). Elevated total IgE indicates atopic predisposition. "
                "Specific IgE (RAST) panel: Latex Class 4 (very high sensitisation) — significant latex allergy, anaphylaxis risk in medical procedures. "
                "Nickel Class 3 (high sensitisation) — confirmed contact allergy. Consistent with patch test results (2+). "
                "Pollen Class 1 (low) — mild environmental sensitisation only. "
                "AI Assessment: Latex allergy is medically significant — all future procedures must use latex-free equipment. "
                "AI Recommendation: EpiPen for latex anaphylaxis risk. Referral to allergist for immunotherapy evaluation. "
                "Doctor Assessment: Patient educated on latex anaphylaxis risk. Latex-free alert added to medical record. "
                "EpiPen prescribed. Allergist referral placed."
            ),
            "pub_text": None,
        },
    ],
    "patient.ngo.thi.xuan@healthai.dev": [
        {
            "test_name": "Skin Biopsy (Psoriatic plaque)",
            "test_type": "other",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"finding": "Epidermal hyperplasia with parakeratosis",       "severity": "moderate"},
                {"finding": "Dilated capillaries in dermal papillae",        "severity": "moderate"},
                {"finding": "Neutrophilic infiltrate (Munro microabscesses)","severity": "moderate"},
            ]),
            "notes": (
                "AI Analysis: Skin biopsy from psoriatic plaque reviewed. Classic histological triad of psoriasis: "
                "1) Epidermal hyperplasia (acanthosis) with regular rete ridge elongation; "
                "2) Parakeratosis with loss of granular layer; "
                "3) Munro microabscesses (neutrophil collections in parakeratotic scale) — pathognomonic for psoriasis. "
                "Dilated tortuous capillaries in dermal papillae (Auspitz sign correlate). No features of psoriatic erythroderma or malignancy. "
                "AI Assessment: Psoriasis vulgaris confirmed histologically. Plaque type. Calculate PASI score to guide treatment escalation. "
                "AI Recommendation: If PASI >10 or inadequate topical response after 3 months, escalate to systemic therapy. "
                "Doctor Assessment: Moderate-to-severe psoriasis based on BSA >10%. Methotrexate 10mg weekly initiated with folic acid 5mg weekly. "
                "PASI will be reassessed at 3 months."
            ),
            "pub_text": (
                "DERMATOPATHOLOGY REPORT — Psoriatic Plaque Biopsy\n"
                "Histology: Epidermal hyperplasia with parakeratosis, Munro microabscesses, dilated dermal papillary capillaries.\n"
                "Diagnosis: Psoriasis Vulgaris (Plaque Type) — histologically confirmed.\n"
                "IMPRESSION: Moderate-to-severe psoriasis confirmed. BSA >10%. "
                "Methotrexate 10mg/week initiated. Folic acid supplementation concurrent. "
                "PASI assessment scheduled at 3-month review."
            ),
        },
        {
            "test_name": "Metabolic Panel (pre-methotrexate screening)",
            "test_type": "blood_panel",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"name": "ALT",         "value": "22",   "unit": "U/L",    "flag": "normal"},
                {"name": "AST",         "value": "19",   "unit": "U/L",    "flag": "normal"},
                {"name": "Creatinine",  "value": "0.85", "unit": "mg/dL",  "flag": "normal"},
                {"name": "WBC",         "value": "7.0",  "unit": "10³/μL", "flag": "normal"},
                {"name": "Platelets",   "value": "245",  "unit": "10³/μL", "flag": "normal"},
            ]),
            "notes": (
                "AI Analysis: Pre-methotrexate screening panel reviewed. "
                "Hepatic safety: ALT 22 and AST 19 both normal — no baseline hepatic dysfunction "
                "(methotrexate is contraindicated if ALT/AST >2x ULN). "
                "Renal safety: Creatinine 0.85 mg/dL, eGFR estimated >80 — adequate renal clearance "
                "(methotrexate is renally cleared; dose reduction needed if eGFR <60). "
                "Haematological safety: WBC 7.0 and Platelets 245 both normal — no pre-treatment cytopenia. "
                "AI Assessment: No contraindications to methotrexate initiation. Baseline established for future monitoring. "
                "AI Recommendation: Monitor CBC and LFTs every 4 weeks for first 3 months, then every 3 months thereafter. "
                "Doctor Assessment: Patient cleared for methotrexate. Methotrexate 10mg weekly started with folic acid 5mg weekly. "
                "Patient counselled on hepatotoxicity, teratogenicity, and infection risk."
            ),
            "pub_text": (
                "PRE-METHOTREXATE SCREENING PANEL\n"
                "ALT: 22 U/L (Normal) | AST: 19 U/L (Normal) — No hepatic contraindication.\n"
                "Creatinine: 0.85 mg/dL (Normal) — No renal contraindication.\n"
                "WBC: 7.0 (Normal) | Platelets: 245 (Normal) — No cytopenia.\n"
                "IMPRESSION: All pre-treatment screening parameters normal. Patient is a suitable candidate for methotrexate therapy. "
                "Methotrexate 10mg/week initiated. Monthly monitoring of CBC and LFTs required."
            ),
        },
    ],
    # ── General Medicine / Orthopedics (Dr. Vo Thanh Tung) ─────────────────
    "patient.mai.thi.lien@healthai.dev": [
        {
            "test_name": "X-Ray Knee (AP + Lateral)",
            "test_type": "imaging",
            "priority":  "routine",
            "file_type": "file",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"finding": "Joint space narrowing medial compartment",   "grade": "Kellgren-Lawrence 2", "severity": "moderate"},
                {"finding": "Osteophyte formation tibial plateau",        "severity": "mild"},
                {"finding": "No fracture or dislocation",                "severity": "normal"},
                {"finding": "Subchondral sclerosis",                     "severity": "mild"},
            ]),
            "notes": (
                "AI Analysis: Medial compartment joint space narrowing with Kellgren-Lawrence Grade 2 changes. "
                "Osteophyte formation at tibial plateau and subchondral sclerosis — classic tricompartmental OA findings in medial-dominant knee. "
                "No fracture, dislocation, or loose body identified. Lateral compartment relatively preserved. "
                "AI Assessment: KL Grade 2 — moderate OA. Conservative management appropriate at this stage. "
                "AI Recommendation: Physiotherapy (strengthening, ROM), NSAIDs (topical or oral), consider intra-articular corticosteroid or hyaluronic acid injection. "
                "Doctor Assessment: Medial compartment OA Grade II. Diclofenac gel 1% applied BD. Physiotherapy referral placed. "
                "If pain not controlled at 3-month review, will consider intra-articular Synvisc injection."
            ),
            "pub_text": (
                "KNEE X-RAY REPORT — AP and Lateral Views\n"
                "Medial compartment: Joint space narrowing — Kellgren-Lawrence Grade 2. Osteophytes at tibial plateau.\n"
                "Subchondral sclerosis: Mild, medial compartment.\n"
                "Lateral compartment: Relatively preserved.\n"
                "IMPRESSION: Medial compartment osteoarthritis, KL Grade 2. No fracture. "
                "Conservative management (physiotherapy, topical NSAIDs) initiated. "
                "Intra-articular injection considered if inadequate response at 3 months."
            ),
        },
        {
            "test_name": "Bone Mineral Density (DEXA Scan)",
            "test_type": "imaging",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "DOCTOR_REVIEW",
            "ai_draft":  json.dumps([
                {"site": "Lumbar spine L1-L4", "T_score": "-1.8", "Z_score": "-0.9", "classification": "Osteopenia"},
                {"site": "Femoral neck",       "T_score": "-1.5", "Z_score": "-0.7", "classification": "Osteopenia"},
            ]),
            "notes": (
                "AI Analysis: DEXA scan confirms osteopenia at both measured sites. "
                "Lumbar spine L1-L4 T-score -1.8 (normal: above -1.0; osteopenia: -1.0 to -2.5; osteoporosis: below -2.5). "
                "Femoral neck T-score -1.5 — also in osteopenic range. Z-scores (age-adjusted) mildly below expected for age but not critically low. "
                "FRAX fracture risk calculation: 10-year probability of major osteoporotic fracture should be calculated using WHO FRAX tool. "
                "AI Recommendation: Calcium 1000-1200mg/day (dietary + supplement) + Vitamin D 2000 IU daily. "
                "Reassess DEXA in 2 years. If T-score worsens to -2.5 or FRAX risk exceeds 20%, initiate bisphosphonate. "
                "Doctor Assessment: Osteopenia confirmed. Lifestyle modification: weight-bearing exercise, smoking cessation, reduce alcohol. "
                "Calcium carbonate 500mg BD + Vitamin D 2000 IU daily started. Repeat DEXA in 2 years."
            ),
            "pub_text": None,
        },
    ],
    "patient.cao.van.toan@healthai.dev": [
        {
            "test_name": "Rheumatoid Factor + Anti-CCP",
            "test_type": "blood_panel",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"name": "Rheumatoid Factor (RF)",   "value": "128",  "unit": "IU/mL", "flag": "high",  "reference_low": "0", "reference_high": "14"},
                {"name": "Anti-CCP antibody",        "value": "86",   "unit": "U/mL",  "flag": "high",  "reference_low": "0", "reference_high": "20"},
                {"name": "ESR",                      "value": "62",   "unit": "mm/hr", "flag": "high",  "reference_low": "0", "reference_high": "20"},
                {"name": "CRP",                      "value": "24",   "unit": "mg/L",  "flag": "high",  "reference_low": "0", "reference_high": "10"},
            ]),
            "notes": (
                "AI Analysis: Seropositive rheumatoid arthritis with very high titre autoantibodies. "
                "RF 128 IU/mL (9x upper limit) and Anti-CCP 86 U/mL (4x upper limit) — both markedly positive. "
                "High Anti-CCP titres specifically predict more aggressive RA with erosive joint disease and extra-articular features. "
                "Elevated ESR 62 mm/hr and CRP 24 mg/L confirm active systemic inflammation. "
                "AI Disease Activity Assessment: High disease activity (DAS28 estimation based on labs). "
                "AI Recommendation: Methotrexate 15mg weekly as first-line DMARD plus bridging prednisolone 10mg OD tapering over 6 weeks. "
                "Folic acid 5mg weekly to reduce MTX side effects. "
                "Doctor Assessment: Seropositive erosive RA — high disease activity. Methotrexate initiated. "
                "Baseline monitoring: CXR (MTX), LFTs, CBC. Rheumatology referral for biologic consideration if MTX fails."
            ),
            "pub_text": (
                "RHEUMATOLOGICAL SEROLOGY REPORT\n"
                "Rheumatoid Factor (RF): 128 IU/mL (HIGH — normal <14)\n"
                "Anti-CCP antibody: 86 U/mL (HIGH — normal <20)\n"
                "ESR: 62 mm/hr (HIGH) | CRP: 24 mg/L (HIGH)\n"
                "IMPRESSION: Seropositive rheumatoid arthritis — high disease activity. "
                "High-titre Anti-CCP predicts aggressive erosive disease. "
                "Methotrexate 15mg weekly + folic acid initiated. Prednisolone bridge therapy. "
                "Baseline monitoring panels ordered. Rheumatology referral placed."
            ),
        },
        {
            "test_name": "DEXA Scan (Osteoporosis monitoring)",
            "test_type": "imaging",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"site": "Lumbar spine L2-L4", "T_score": "-2.6", "Z_score": "-1.2", "classification": "Osteoporosis"},
                {"site": "Total hip",          "T_score": "-2.3", "Z_score": "-1.0", "classification": "Osteoporosis"},
            ]),
            "notes": (
                "AI Analysis: DEXA scan confirms osteoporosis at both measured sites — significantly below osteopenic threshold. "
                "Lumbar spine L2-L4 T-score -2.6 (below -2.5 = osteoporosis) and total hip -2.3. "
                "Combined with corticosteroid use in RA (prednisolone bridge therapy) — glucocorticoid-induced osteoporosis risk is compounded. "
                "Z-score -1.2 at spine suggests some disease contribution beyond age-related bone loss. "
                "FRAX 10-year major fracture risk likely elevated (>20% threshold requires treatment regardless of T-score). "
                "AI Recommendation: Bisphosphonate therapy (alendronate 70mg weekly or zoledronic acid annual IV). "
                "Calcium 1200mg/day + Vitamin D 2000-4000 IU/day. Hip protector pads advised for fall risk. "
                "Doctor Assessment: Osteoporosis confirmed — high fracture risk in RA patient on steroids. "
                "Alendronate 70mg weekly initiated with Calcium 1200mg + Vit D 2000 IU daily. Falls prevention referral."
            ),
            "pub_text": (
                "DEXA BONE DENSITY REPORT\n"
                "Lumbar spine L2-L4: T-score -2.6 (OSTEOPOROSIS) | Z-score -1.2\n"
                "Total hip: T-score -2.3 (OSTEOPOROSIS) | Z-score -1.0\n"
                "IMPRESSION: Osteoporosis at both measured sites. High fracture risk compounded by corticosteroid use (RA therapy). "
                "Bisphosphonate therapy (Alendronate 70mg weekly) initiated. Calcium + Vitamin D supplementation. "
                "Annual DEXA monitoring. Falls prevention programme referral."
            ),
        },
    ],
    # ── Respiratory patients (Dr. Pham Thi Lan Huong) ─────────────────────
    "patient.pham.van.khang@healthai.dev": [
        {
            "test_name": "Arterial Blood Gas (ABG)",
            "test_type": "blood_panel",
            "priority":  "urgent",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"name": "pH",    "value": "7.35", "unit": "",      "flag": "normal", "reference_low": "7.35", "reference_high": "7.45"},
                {"name": "PaO2",  "value": "62",   "unit": "mmHg",  "flag": "low",    "reference_low": "80",   "reference_high": "100"},
                {"name": "PaCO2", "value": "48",   "unit": "mmHg",  "flag": "high",   "reference_low": "35",   "reference_high": "45"},
                {"name": "HCO3",  "value": "27",   "unit": "mEq/L", "flag": "normal", "reference_low": "22",   "reference_high": "26"},
                {"name": "SaO2",  "value": "92",   "unit": "%",     "flag": "low",    "reference_low": "95",   "reference_high": "100"},
            ]),
            "notes": (
                "AI Analysis: Arterial blood gas reveals compensated type 2 respiratory failure pattern. "
                "pH 7.35 — low normal (compensated). PaO2 62 mmHg — hypoxia (mild, target >60 for COPD patients). "
                "PaCO2 48 mmHg — elevated above normal (35-45) — CO2 retention = type 2 (hypercapnic) respiratory failure. "
                "HCO3 27 mEq/L — elevated (metabolic compensation for chronic CO2 retention). SaO2 92% — borderline. "
                "AI Assessment: Chronic hypercapnic respiratory failure consistent with severe COPD (GOLD Stage III-IV). "
                "AI Risk: Avoid high-flow oxygen (drives up PaCO2 further in COPD via Haldane effect). Target SaO2 88-92%. "
                "AI Recommendation: Low-flow controlled oxygen (1-2 L/min via Venturi mask). Consider NIV (BiPAP). "
                "Doctor Assessment: Controlled oxygen therapy initiated at 24% FiO2 (Venturi). BiPAP ordered if PaCO2 rises further. Nebulised bronchodilators running."
            ),
            "pub_text": (
                "ARTERIAL BLOOD GAS REPORT\n"
                "pH: 7.35 (Low normal — compensated)\n"
                "PaO2: 62 mmHg (LOW — mild hypoxia, target >60 for COPD)\n"
                "PaCO2: 48 mmHg (HIGH — CO2 retention)\n"
                "HCO3: 27 mEq/L (Elevated — metabolic compensation)\n"
                "SaO2: 92% (Borderline — target 88-92% in COPD)\n"
                "IMPRESSION: Compensated Type 2 Respiratory Failure (hypoxic-hypercapnic). "
                "Consistent with acute-on-chronic COPD exacerbation. "
                "Controlled oxygen therapy and nebulised bronchodilators initiated. BiPAP on standby."
            ),
        },
        {
            "test_name": "Sputum Culture & Sensitivity",
            "test_type": "other",
            "priority":  "urgent",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"organism": "Haemophilus influenzae", "colony_count": "10⁵ CFU/mL", "sensitivity": {"amoxicillin-clavulanate": "sensitive", "azithromycin": "sensitive", "ciprofloxacin": "sensitive"}},
                {"organism": "Normal oral flora",      "colony_count": "moderate"},
            ]),
            "notes": (
                "AI Analysis: Sputum culture identifies Haemophilus influenzae — one of the three most common COPD exacerbation pathogens "
                "(alongside Streptococcus pneumoniae and Moraxella catarrhalis). "
                "Colony count 10^5 CFU/mL — significant growth (>10^4 = significant for lower respiratory tract). "
                "Sensitivity pattern: amoxicillin-clavulanate (sensitive), azithromycin (sensitive), ciprofloxacin (sensitive). "
                "Not resistant to beta-lactams in this case — amox-clav is the preferred first-line choice for H. influenzae COPD exacerbation. "
                "AI Recommendation: Amoxicillin-clavulanate 625mg TID x 5-7 days. Alternatively doxycycline or azithromycin if penicillin allergy. "
                "Doctor Assessment: H. influenzae AECOPD confirmed. Amoxicillin-clavulanate 625mg TID x 7 days started. "
                "Prednisolone 30mg OD x 5 days (steroid course for AECOPD). Clinical reassessment in 48 hours."
            ),
            "pub_text": (
                "SPUTUM CULTURE & SENSITIVITY REPORT\n"
                "Organism: Haemophilus influenzae — 10^5 CFU/mL (significant growth)\n"
                "Sensitivity: Amoxicillin-clavulanate (S), Azithromycin (S), Ciprofloxacin (S)\n"
                "Normal flora: Moderate oral contamination\n"
                "IMPRESSION: H. influenzae isolated — significant COPD exacerbation pathogen. "
                "Amoxicillin-clavulanate 625mg TID x 7 days initiated. "
                "Oral prednisolone 30mg OD x 5 days added for AECOPD management."
            ),
        },
    ],
    "patient.luu.thi.mai@healthai.dev": [
        {
            "test_name": "Spirometry (Pre & Post Bronchodilator)",
            "test_type": "other",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"name": "FEV1 (pre-BD)",    "value": "68",   "unit": "%predicted", "flag": "low"},
                {"name": "FEV1 (post-BD)",   "value": "83",   "unit": "%predicted", "flag": "normal"},
                {"name": "FVC",              "value": "88",   "unit": "%predicted", "flag": "normal"},
                {"name": "FEV1/FVC",         "value": "0.76", "unit": "ratio",      "flag": "normal"},
                {"name": "Reversibility",    "value": "+22",  "unit": "%",          "flag": "significant"},
            ]),
            "notes": (
                "AI Analysis: Pre and post-bronchodilator spirometry performed. "
                "Pre-BD FEV1 68% predicted — mild-to-moderate obstruction. Post-BD FEV1 83% predicted — improvement of 15 percentage points. "
                "Reversibility: +22% relative improvement (>12% absolute + >200mL = clinically significant per GINA/ATS criteria). "
                "FVC 88% and FEV1/FVC 0.76 — within normal limits, confirming reversible obstruction (asthma) rather than COPD (which would have persistently low FEV1/FVC post-BD). "
                "AI Assessment: Confirmed asthma (significant reversibility distinguishes from COPD). Moderate airflow limitation pre-BD. "
                "AI Recommendation: GINA Step 3 therapy — ICS/LABA combination (budesonide/formoterol 160/4.5mcg BD). SABA as reliever. "
                "Doctor Assessment: Asthma confirmed with significant BD response. Initiated Symbicort (budesonide/formoterol) Turbuhaler 2 puffs BD. "
                "SABA salbutamol for relief. Asthma action plan provided. Review in 4 weeks."
            ),
            "pub_text": (
                "SPIROMETRY REPORT — Pre and Post Bronchodilator\n"
                "Pre-BD FEV1: 68% predicted (Mild-moderate obstruction)\n"
                "Post-BD FEV1: 83% predicted (Reversibility +22% — SIGNIFICANT)\n"
                "FVC: 88% (Normal) | FEV1/FVC: 0.76 (Normal)\n"
                "IMPRESSION: Significant bronchodilator reversibility confirming asthma diagnosis. "
                "ICS/LABA combination therapy (Symbicort) initiated. GINA Step 3 management. "
                "Written asthma action plan provided to patient."
            ),
        },
        {
            "test_name": "FeNO (Fractional Exhaled Nitric Oxide)",
            "test_type": "other",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "DOCTOR_REVIEW",
            "ai_draft":  json.dumps([
                {"name": "FeNO",    "value": "42", "unit": "ppb", "flag": "high", "reference_low": "0", "reference_high": "25"},
                {"interpretation": "High eosinophilic airway inflammation — strong predictor of ICS response"},
            ]),
            "notes": (
                "AI Analysis: FeNO (Fractional Exhaled Nitric Oxide) 42 ppb — elevated (normal <25 ppb, borderline 25-50, high >50). "
                "FeNO reflects eosinophilic (Type 2) airway inflammation. Values >25 ppb predict: "
                "1) Eosinophilic asthma phenotype (responds well to ICS), "
                "2) High likelihood of ICS response (>80% response rate at FeNO >40 ppb), "
                "3) Increased risk of asthma exacerbation if ICS is stopped. "
                "Combined with reversible spirometry and symptoms: eosinophilic asthma phenotype confirmed. "
                "AI Recommendation: ICS/LABA combination is optimal therapy. If FeNO remains elevated >25 ppb on adequate ICS, "
                "consider add-on anti-IL-4 (dupilumab) or anti-IL-5 (mepolizumab) biologics. "
                "Doctor Assessment: FeNO 42 ppb confirms eosinophilic phenotype — excellent ICS response predicted. "
                "Continued Symbicort 2 puffs BD. Reassess FeNO at 6-week follow-up."
            ),
            "pub_text": None,
        },
    ],
    # ── Nephrology patients (Dr. Hoang Van Minh) ───────────────────────────
    "patient.dinh.thi.lan@healthai.dev": [
        {
            "test_name": "Comprehensive Metabolic Panel",
            "test_type": "blood_panel",
            "priority":  "urgent",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"name": "Creatinine",   "value": "1.8",  "unit": "mg/dL",  "flag": "high",   "reference_low": "0.5", "reference_high": "1.1"},
                {"name": "BUN",          "value": "28",   "unit": "mg/dL",  "flag": "high",   "reference_low": "7",   "reference_high": "20"},
                {"name": "eGFR",         "value": "42",   "unit": "mL/min", "flag": "low",    "reference_low": "60",  "reference_high": "120"},
                {"name": "HbA1c",        "value": "7.8",  "unit": "%",      "flag": "high",   "reference_low": "0",   "reference_high": "6.5"},
                {"name": "Potassium",    "value": "5.2",  "unit": "mEq/L",  "flag": "high",   "reference_low": "3.5", "reference_high": "5.0"},
                {"name": "Bicarbonate",  "value": "20",   "unit": "mEq/L",  "flag": "low",    "reference_low": "22",  "reference_high": "29"},
            ]),
            "notes": (
                "AI Analysis: Comprehensive metabolic panel shows multi-system complications of diabetic CKD. "
                "Creatinine 1.8 mg/dL (female reference 0.5-1.1) and eGFR 42 mL/min — CKD Stage 3a (moderate). "
                "HbA1c 7.8% — suboptimal glycaemic control (target <7.0% for CKD patients to slow progression). "
                "Mild hyperkalemia K+ 5.2 mEq/L — dietary restriction of potassium indicated. ACE inhibitor dose should be assessed. "
                "Metabolic acidosis: HCO3 20 mEq/L (normal 22-29) — early CKD-related acidosis, worsens bone disease and muscle wasting. "
                "AI Recommendation: Sodium bicarbonate supplement if HCO3 <20. Optimise glycaemia with DPP4 inhibitor or SGLT2 (dose-adjusted for eGFR). "
                "Doctor Assessment: Multi-modal management: sodium bicarbonate 500mg BD started, dietary K+ restriction counselling. "
                "Metformin dose reviewed (safe at eGFR 42). Diabetologist co-management arranged."
            ),
            "pub_text": (
                "COMPREHENSIVE METABOLIC PANEL REPORT\n"
                "Creatinine: 1.8 mg/dL (HIGH) | eGFR: 42 mL/min (CKD Stage 3a)\n"
                "HbA1c: 7.8% (HIGH — target <7.0%)\n"
                "Potassium: 5.2 mEq/L (HIGH — dietary restriction) | Bicarbonate: 20 mEq/L (LOW — metabolic acidosis)\n"
                "IMPRESSION: CKD Stage 3a in T2DM patient with metabolic complications (mild hyperkalemia, metabolic acidosis, suboptimal glycaemia). "
                "Sodium bicarbonate initiated. Dietary counselling provided. Glycaemia optimisation arranged with diabetologist."
            ),
        },
        {
            "test_name": "24-hr Urine Protein",
            "test_type": "urine",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"name": "24-hr urine volume",   "value": "1800", "unit": "mL",   "flag": "normal"},
                {"name": "Total protein",        "value": "890",  "unit": "mg/24hr","flag": "high", "reference_low": "0", "reference_high": "150"},
                {"name": "Albumin (24-hr)",      "value": "620",  "unit": "mg/24hr","flag": "high", "reference_low": "0", "reference_high": "30"},
            ]),
            "notes": (
                "AI Analysis: 24-hour urine protein quantification — significant proteinuria. "
                "Total protein 890 mg/24hr — well above the 150 mg/24hr upper limit. Albuminuria 620 mg/24hr — macroalbuminuria range (>300 mg/24hr). "
                "This is frank diabetic nephropathy (DN Stage 3). Proteinuria at this level (>500 mg/24hr) is associated with: "
                "1) Rapid eGFR decline (5-10 mL/min/year without optimal management); "
                "2) Significantly elevated cardiovascular mortality risk; "
                "3) Increased risk of nephrotic syndrome progression. "
                "AI Recommendation: Maximise RAAS blockade (ACE inhibitor + ARB combination controversial — specialist decision). "
                "SGLT2 inhibitor (empagliflozin/dapagliflozin) has proven renoprotective benefit in T2DM with proteinuria. "
                "Strict BP control <130/80 mmHg. Restrict dietary protein to 0.8g/kg/day. "
                "Doctor Assessment: Empagliflozin 10mg added to regimen (DKD CREDENCE-class benefit). "
                "Nephrology referral for specialist management. Finerenone (non-steroidal MRA) under consideration."
            ),
            "pub_text": (
                "24-HOUR URINE PROTEIN QUANTIFICATION\n"
                "Urine volume: 1800 mL/24hr\n"
                "Total protein: 890 mg/24hr (HIGH — normal <150)\n"
                "Albumin: 620 mg/24hr (MACROALBUMINURIA — >300 mg/24hr threshold)\n"
                "IMPRESSION: Significant proteinuria at macroalbuminuria level — frank diabetic nephropathy (Stage 3 DN). "
                "High cardiovascular and renal risk. RAAS blockade maximised. SGLT2 inhibitor (empagliflozin) added. "
                "Nephrology referral placed."
            ),
        },
    ],
    "patient.nguyen.thi.thanh@healthai.dev": [
        {
            "test_name": "Urine Culture & Sensitivity",
            "test_type": "urine",
            "priority":  "urgent",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"organism": "Escherichia coli",     "colony_count": ">10⁵ CFU/mL", "sensitivity": {"trimethoprim-sulfamethoxazole": "resistant", "ciprofloxacin": "sensitive", "nitrofurantoin": "sensitive", "fosfomycin": "sensitive"}},
            ]),
            "notes": (
                "AI Analysis: Urine culture positive for E. coli — the most common uropathogen (responsible for 80-85% of uncomplicated UTIs). "
                "Colony count >10^5 CFU/mL — clearly significant (threshold for diagnosis is >10^3 for symptomatic patients, >10^5 for asymptomatic screening). "
                "Antimicrobial sensitivity: TMP-SMX (trimethoprim-sulfamethoxazole) RESISTANT — this is increasingly common globally. "
                "Nitrofurantoin: SENSITIVE — 1st choice for uncomplicated lower UTI (cystitis). Ciprofloxacin: SENSITIVE — reserve for complicated UTI. "
                "Fosfomycin: SENSITIVE — excellent oral option. "
                "AI Assessment: Recurrent UTI in nephrology patient — consider investigation for anatomical abnormality or immunosuppression. "
                "AI Recommendation: Nitrofurantoin 100mg BD x 5 days (macrocrystalline). If recurrent (>3/year), consider prophylaxis with nitrofurantoin 50mg OD (nightly). "
                "Doctor Assessment: Nitrofurantoin 100mg BD x 5 days prescribed. "
                "Urine culture sent for test-of-cure in 1 week. Cranberry prophylaxis discussed. Nephrology to review for anatomical/functional cause."
            ),
            "pub_text": (
                "URINE CULTURE & SENSITIVITY REPORT\n"
                "Organism: Escherichia coli — >10^5 CFU/mL (Significant growth)\n"
                "Resistance: Trimethoprim-sulfamethoxazole — RESISTANT\n"
                "Sensitive: Nitrofurantoin (S), Ciprofloxacin (S), Fosfomycin (S)\n"
                "IMPRESSION: E. coli UTI with TMP-SMX resistance. Nitrofurantoin 100mg BD x 5 days prescribed. "
                "Test-of-cure culture in 1 week. Recurrent UTI investigation planned."
            ),
        },
        {
            "test_name": "Renal Ultrasound",
            "test_type": "imaging",
            "priority":  "routine",
            "file_type": "file",
            "status":    "DOCTOR_REVIEW",
            "ai_draft":  json.dumps([
                {"finding": "Right kidney 10.2 cm, normal echogenicity",          "severity": "normal"},
                {"finding": "Left kidney 10.5 cm, normal echogenicity",           "severity": "normal"},
                {"finding": "No hydronephrosis or calculi",                       "severity": "normal"},
                {"finding": "Mild bladder wall thickening (post-void residual 45 mL)", "severity": "mild"},
            ]),
            "notes": (
                "AI Analysis: Renal ultrasound provides anatomical assessment complementing the urine culture findings. "
                "Both kidneys: normal size (right 10.8cm, left 11.2cm — normal 10-12cm) with preserved corticomedullary differentiation. "
                "No hydronephrosis, no calculi, no solid masses. Bladder wall thickening 4mm (borderline — normal <3mm when full) noted. "
                "Post-void residual volume 45 mL (borderline — significant if >50mL in adults, may indicate functional bladder dysfunction). "
                "AI Assessment: No structural upper urinary tract cause for recurrent UTI identified. "
                "Mild bladder wall thickening may represent: chronic cystitis, bladder outlet obstruction, or early neurogenic bladder. "
                "AI Recommendation: Urodynamic study if PVR persistently elevated. Cystoscopy if recurrent UTI continues. "
                "Doctor Assessment: Upper tracts normal. Bladder wall changes likely chronic cystitis. "
                "Voiding diary requested. Pelvic floor physiotherapy referral. Urodynamics if no improvement."
            ),
            "pub_text": None,
        },
    ],
    # ── Hematology patients (Dr. Nguyen Thi Hue Linh) ──────────────────────
    "patient.vu.thi.hang@healthai.dev": [
        {
            "test_name": "Iron Studies Panel",
            "test_type": "blood_panel",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"name": "Serum Iron",         "value": "38",  "unit": "μg/dL",  "flag": "low",   "reference_low": "60",  "reference_high": "170"},
                {"name": "TIBC",               "value": "420", "unit": "μg/dL",  "flag": "high",  "reference_low": "250", "reference_high": "370"},
                {"name": "Transferrin Sat.",   "value": "9",   "unit": "%",       "flag": "low",   "reference_low": "20",  "reference_high": "50"},
                {"name": "Ferritin",           "value": "5",   "unit": "ng/mL",  "flag": "low",   "reference_low": "12",  "reference_high": "150"},
            ]),
            "notes": (
                "AI Analysis: Iron studies confirm absolute iron deficiency — the most common nutritional deficiency worldwide. "
                "Serum iron 28 mcg/dL (LOW — normal 60-170). Serum ferritin 5 ng/mL (SEVERELY LOW — normal 12-150 female). "
                "TIBC (total iron binding capacity) 520 mcg/dL (HIGH — normal 250-370) — reflecting upregulated transferrin production in iron-depleted state. "
                "Transferrin saturation: Iron / TIBC = 28/520 = 5.4% (severely low — normal 20-50%). "
                "AI Assessment: Absolute iron deficiency — all four markers consistent. No response to oral iron (documented in history) likely due to malabsorption, GI intolerance, or ongoing blood loss. "
                "AI Recommendation: IV iron supplementation — Ferric carboxymaltose (Ferinject) 500-1000mg IV infusion. "
                "Investigate ongoing blood loss: GI scope if not done. "
                "Doctor Assessment: IV Ferinject 500mg ordered. Pre-infusion test dose administered. "
                "Upper GI endoscopy referral placed. Repeat CBC + iron studies in 4 weeks."
            ),
            "pub_text": (
                "IRON STUDIES REPORT\n"
                "Serum Iron: 28 mcg/dL (LOW — normal 60-170)\n"
                "Ferritin: 5 ng/mL (SEVERELY LOW — normal 12-150)\n"
                "TIBC: 520 mcg/dL (HIGH — normal 250-370)\n"
                "Transferrin Saturation: 5.4% (SEVERELY LOW — normal 20-50%)\n"
                "IMPRESSION: Absolute iron deficiency confirmed. Oral iron inadequate (failed prior course). "
                "IV iron (Ferric carboxymaltose 500mg) administered. GI blood loss investigation initiated."
            ),
        },
        {
            "test_name": "Reticulocyte Count + Response Index",
            "test_type": "blood_panel",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "DOCTOR_REVIEW",
            "ai_draft":  json.dumps([
                {"name": "Reticulocyte %",           "value": "1.2",  "unit": "%",    "flag": "normal"},
                {"name": "Reticulocyte count (abs)", "value": "38",   "unit": "10³/μL","flag": "low"},
                {"name": "Reticulocyte Production Index (RPI)", "value": "0.8", "unit": "", "flag": "low", "reference_low": "2.0"},
            ]),
            "notes": (
                "AI Analysis: Reticulocyte production index (RPI) quantifies the marrow's reticulocyte response relative to degree of anaemia. "
                "RPI <2 in the context of anaemia indicates INADEQUATE marrow response — bone marrow is not compensating sufficiently. "
                "Expected in iron deficiency: the marrow lacks the substrate (iron) to produce red cells at the required rate. "
                "Absolute reticulocyte count: 28,000/μL (normal 50,000-150,000) — absolute reticulocytopenia. "
                "Corrected reticulocyte count: 0.7% — well below 2% threshold for appropriate response. "
                "AI Assessment: Hypoproliferative anaemia pattern — consistent with iron deficiency anaemia. "
                "Differentials ruled out: haemolytic anaemia (would show high RPI); aplastic anaemia (would also have low WBC/platelets). "
                "AI Recommendation: Expect reticulocyte surge (reticulocyte crisis) at 7-10 days post IV iron, then rise in Hb at 2-4 weeks. "
                "Doctor Assessment: RPI <2 consistent with iron deficiency aetiology. "
                "Reticulocyte surge expected in 7-10 days. Repeat CBC day 14, day 28 post-Ferinject."
            ),
            "pub_text": None,
        },
    ],
    # ── Endocrinology patients (Dr. Tran Van Phuong) ───────────────────────
    "patient.bui.thi.linh@healthai.dev": [
        {
            "test_name": "HbA1c + Fasting Insulin + HOMA-IR",
            "test_type": "blood_panel",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"name": "HbA1c",         "value": "9.1",  "unit": "%",       "flag": "high",  "reference_low": "0",  "reference_high": "6.5"},
                {"name": "Fasting Glucose","value": "212",  "unit": "mg/dL",   "flag": "high",  "reference_low": "70", "reference_high": "100"},
                {"name": "Fasting Insulin","value": "28",   "unit": "μIU/mL",  "flag": "high",  "reference_low": "2",  "reference_high": "25"},
                {"name": "HOMA-IR",       "value": "14.6", "unit": "",         "flag": "high",  "reference_low": "0",  "reference_high": "3.0"},
            ]),
            "notes": (
                "AI Analysis: HbA1c 9.1% reflects average blood glucose of approximately 12.6 mmol/L over past 3 months — severely uncontrolled. "
                "HOMA-IR 14.6 (normal <2.5) — profound insulin resistance. This level of HOMA-IR indicates: "
                "1) Peripheral insulin resistance (muscle, adipose tissue); "
                "2) Likely requiring dose increase or drug class change; "
                "3) Risk of beta-cell exhaustion if chronically untreated. "
                "Current HbA1c trend worsening — current metformin + sulphonylurea combination insufficient. "
                "AI Recommendation: Triple therapy — add SGLT2 inhibitor (empagliflozin 10mg) for: "
                "cardiovascular benefit (EMPA-REG outcome), renal protection, weight loss (~2-4kg), additional HbA1c lowering (~0.8%). "
                "Alternatively GLP-1 RA (semaglutide) if ASCVD risk high. "
                "Doctor Assessment: Empagliflozin 10mg OD added. Dietary counselling rescheduled. "
                "Patient educated on SGLT2 mechanism and genital hygiene. Review HbA1c in 3 months."
            ),
            "pub_text": (
                "HbA1c + INSULIN RESISTANCE PANEL\n"
                "HbA1c: 9.1% (SEVERELY HIGH — target <7.0%)\n"
                "Fasting insulin: 24.6 mU/L (HIGH — normal 3-15) | Fasting glucose: 9.8 mmol/L (HIGH)\n"
                "HOMA-IR: 14.6 (VERY HIGH — normal <2.5; insulin resistance threshold >3.0)\n"
                "IMPRESSION: Severely uncontrolled T2DM with marked insulin resistance. "
                "SGLT2 inhibitor (empagliflozin 10mg OD) added for glycaemic control and organ protection. "
                "Dietary optimisation and HbA1c reassessment in 3 months."
            ),
        },
        {
            "test_name": "Lipid Panel + Microalbumin",
            "test_type": "blood_panel",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"name": "Total Cholesterol",    "value": "258", "unit": "mg/dL", "flag": "high",  "reference_low": "0",  "reference_high": "200"},
                {"name": "LDL",                  "value": "178", "unit": "mg/dL", "flag": "high",  "reference_low": "0",  "reference_high": "100"},
                {"name": "HDL",                  "value": "35",  "unit": "mg/dL", "flag": "low",   "reference_low": "50", "reference_high": "60"},
                {"name": "Triglycerides",        "value": "310", "unit": "mg/dL", "flag": "high",  "reference_low": "0",  "reference_high": "150"},
                {"name": "Urine ACR",            "value": "52",  "unit": "mg/g",  "flag": "high",  "reference_low": "0",  "reference_high": "30"},
            ]),
            "notes": (
                "AI Analysis: Severe atherogenic dyslipidemia profile in T2DM with microalbuminuria — extremely high cardiovascular risk. "
                "LDL 178 mg/dL (target in T2DM with CKD should be <70 mg/dL — this is 2.5x above target). "
                "Triglycerides 310 mg/dL (significantly elevated — normal <150 mg/dL; pancreatitis risk >500 mg/dL). "
                "HDL 32 mg/dL (LOW — normal >40 male, >50 female) — low HDL compounds cardiovascular risk. "
                "Urine ACR 52 mg/g (MICROALBUMINURIA range 30-300 mg/g) — early nephropathy marker, also independent cardiovascular risk. "
                "AI Assessment: Atherogenic triad (high LDL, high TG, low HDL) in a T2DM patient — extreme 10-year ASCVD risk. "
                "AI Recommendation: Maximise high-intensity statin (rosuvastatin 40mg or atorvastatin 80mg). "
                "Fenofibrate 145mg OD if TG persists >200 after statin. Omega-3 fatty acids 4g/day for severe hypertriglyceridemia. "
                "Doctor Assessment: Rosuvastatin increased to 40mg. Fenofibrate 145mg added for hypertriglyceridemia. "
                "Omega-3 (Lovaza 4g) considered. Recheck lipids + LFTs in 6 weeks."
            ),
            "pub_text": (
                "LIPID PANEL + URINE ACR REPORT\n"
                "LDL cholesterol: 178 mg/dL (VERY HIGH — target <70 in T2DM with CKD)\n"
                "Triglycerides: 310 mg/dL (HIGH — normal <150)\n"
                "HDL cholesterol: 32 mg/dL (LOW — normal >50 female)\n"
                "Urine ACR: 52 mg/g (MICROALBUMINURIA — range 30-300 mg/g)\n"
                "IMPRESSION: Severe mixed atherogenic dyslipidemia with microalbuminuria in T2DM — extreme ASCVD risk. "
                "High-intensity statin (rosuvastatin 40mg) and fenofibrate initiated. "
                "Lipid + LFT reassessment at 6 weeks."
            ),
        },
    ],
    "patient.do.van.hung@healthai.dev": [
        {
            "test_name": "Thyroid Function Panel (Follow-up)",
            "test_type": "blood_panel",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"name": "TSH",       "value": "3.8",  "unit": "mIU/L", "flag": "normal", "reference_low": "0.4", "reference_high": "4.0"},
                {"name": "Free T4",   "value": "1.1",  "unit": "ng/dL",  "flag": "normal", "reference_low": "0.8", "reference_high": "1.8"},
                {"name": "Anti-TPO",  "value": "480",  "unit": "IU/mL",  "flag": "high",   "reference_low": "0",   "reference_high": "35"},
            ]),
            "notes": (
                "AI Analysis: Thyroid function tests show successful biochemical euthyroidism on levothyroxine replacement therapy. "
                "TSH 2.1 mIU/L — within target range (0.5-4.0 mIU/L for stable hypothyroidism; some prefer 0.5-2.5 mIU/L). "
                "FT4 15 pmol/L — within normal range (12-22 pmol/L). FT3 4.5 pmol/L — normal. "
                "Anti-TPO antibody 480 IU/mL (STRONGLY POSITIVE — normal <35 IU/mL) — confirms autoimmune aetiology (Hashimoto thyroiditis). "
                "AI Assessment: Good biochemical control on current levothyroxine dose. Anti-TPO will likely remain elevated lifelong — "
                "this is not a marker of treatment inadequacy but rather of the underlying autoimmune condition. "
                "AI Note: Monitor for atrophic thyroiditis progression over years (may need dose increase). "
                "AI Recommendation: Continue current levothyroxine dose. Annual TFT monitoring. Check vitamin D and B12 (associated autoimmune deficiencies). "
                "Doctor Assessment: Excellent thyroid control. No dose change. Annual TFT + anti-TPO. Vitamin D 1000 IU supplemented."
            ),
            "pub_text": (
                "THYROID FUNCTION PANEL — FOLLOW-UP\n"
                "TSH: 2.1 mIU/L (NORMAL — target 0.5-2.5 on replacement)\n"
                "Free T4: 15 pmol/L (Normal) | Free T3: 4.5 pmol/L (Normal)\n"
                "Anti-TPO antibody: 480 IU/mL (POSITIVE — confirms Hashimoto thyroiditis)\n"
                "IMPRESSION: Biochemical euthyroidism achieved on levothyroxine replacement. "
                "Hashimoto thyroiditis aetiology confirmed by elevated Anti-TPO. "
                "Current therapy maintained. Annual TFT monitoring. Vitamin D supplementation added."
            ),
        },
        {
            "test_name": "Lipid Profile (dyslipidemia monitoring)",
            "test_type": "blood_panel",
            "priority":  "routine",
            "file_type": "manual",
            "status":    "DOCTOR_REVIEW",
            "ai_draft":  json.dumps([
                {"name": "Total Cholesterol", "value": "235", "unit": "mg/dL", "flag": "high",  "reference_low": "0",  "reference_high": "200"},
                {"name": "LDL",               "value": "155", "unit": "mg/dL", "flag": "high",  "reference_low": "0",  "reference_high": "130"},
                {"name": "HDL",               "value": "42",  "unit": "mg/dL", "flag": "normal","reference_low": "40", "reference_high": "60"},
                {"name": "Triglycerides",     "value": "195", "unit": "mg/dL", "flag": "high",  "reference_low": "0",  "reference_high": "150"},
            ]),
            "notes": (
                "AI Analysis: Lipid panel shows mixed dyslipidemia in the context of treated hypothyroidism. "
                "LDL 148 mg/dL (ELEVATED — desirable <100 mg/dL, borderline high 130-159 mg/dL). "
                "Total cholesterol 242 mg/dL (HIGH — normal <200 mg/dL). "
                "Triglycerides 185 mg/dL (BORDERLINE HIGH — normal <150 mg/dL). HDL 42 mg/dL (low-normal). "
                "AI Note: Hypothyroidism itself causes secondary dyslipidemia — TSH should be fully optimised before initiating lipid-lowering therapy. "
                "If TSH is now normal (2.1 mIU/L), this dyslipidemia is partially primary (familial or dietary). "
                "AI Assessment: After 3 months of optimised thyroid replacement, if dyslipidemia persists, statin therapy is warranted. "
                "AI Recommendation: Lifestyle: heart-healthy diet, 150 min/week aerobic exercise. Reassess lipids in 3 months. "
                "If LDL remains >130, initiate atorvastatin 20mg. "
                "Doctor Assessment: Optimise thyroid dose first. Dietary counselling provided. Lipid reassessment scheduled in 3 months."
            ),
            "pub_text": None,
        },
    ],
    "patient.truong.thi.mai@healthai.dev": [
        {
            "test_name": "Thyroid Function + TRAb",
            "test_type": "blood_panel",
            "priority":  "urgent",
            "file_type": "manual",
            "status":    "PUBLISHED",
            "ai_draft":  json.dumps([
                {"name": "TSH",     "value": "0.02", "unit": "mIU/L", "flag": "low",  "reference_low": "0.4",  "reference_high": "4.0"},
                {"name": "Free T4", "value": "4.8",  "unit": "ng/dL",  "flag": "high", "reference_low": "0.8",  "reference_high": "1.8"},
                {"name": "Free T3", "value": "12.2", "unit": "pg/mL",  "flag": "high", "reference_low": "2.3",  "reference_high": "4.2"},
                {"name": "TRAb",    "value": "8.4",  "unit": "IU/L",   "flag": "high", "reference_low": "0",    "reference_high": "1.75"},
            ]),
            "notes": (
                "AI Analysis: Graves' disease confirmed by constellation of biochemical and serological findings. "
                "TSH 0.02 mIU/L (SUPPRESSED — normal 0.5-4.0) — pituitary feedback loop overridden by autonomous thyroid stimulation. "
                "FT4 4.8 ng/dL (MARKEDLY ELEVATED — normal 0.8-1.8) and FT3 12.2 pg/mL (ELEVATED — normal 2.3-4.2). "
                "TRAb (TSH Receptor Antibody) 8.4 IU/L (STRONGLY POSITIVE — normal <1.8 IU/L) — pathognomonic for Graves' disease. "
                "AI Assessment: Overt hyperthyroidism with positive TRAb = Graves' disease (not toxic nodular goitre or factitious thyrotoxicosis). "
                "TRAb elevation also predicts Graves' ophthalmopathy (GO) risk — ophthalmology screening mandatory. "
                "AI Recommendation: Carbimazole 20-40mg daily (titration-block method). Propranolol 40mg BD for symptom control. "
                "Reassess TFT in 4-6 weeks. Definitive therapy discussion at 6 months: radioiodine or thyroidectomy. "
                "Doctor Assessment: Carbimazole 20mg OD + propranolol 40mg BD started. Ophthalmology referral for GO screening. "
                "Patient counselled on monitoring for agranulocytosis (sore throat protocol). TFT review in 6 weeks."
            ),
            "pub_text": (
                "THYROID PANEL + TRAb REPORT\n"
                "TSH: 0.02 mIU/L (SEVERELY SUPPRESSED)\n"
                "Free T4: 4.8 ng/dL (MARKEDLY ELEVATED) | Free T3: 12.2 pg/mL (ELEVATED)\n"
                "TRAb (TSH Receptor Antibody): 8.4 IU/L (STRONGLY POSITIVE — normal <1.8)\n"
                "IMPRESSION: Graves' disease confirmed — overt hyperthyroidism with positive TRAb antibody. "
                "Carbimazole 20mg OD + propranolol 40mg BD initiated. "
                "Ophthalmology referral for Graves' ophthalmopathy screening. "
                "TFT reassessment in 6 weeks. Definitive therapy planning at 6 months."
            ),
        },
    ],
}

# ── Helper functions ─────────────────────────────────────────────────────────

def _doc_email_to_specialty(doc_email: str) -> str | None:
    for doc in DOCTORS:
        if doc["email"] == doc_email:
            return doc["specialty"]
    return None


def _specialty_to_dept(specialty_name: str | None) -> str | None:
    if specialty_name is None:
        return None
    for sp in SPECIALTIES:
        if sp["name"] == specialty_name:
            return sp.get("dept")
    return None


# ── Labs for today's IN_PROGRESS appointments (DOCTOR_REVIEW — ready to verify) ─
IN_PROGRESS_LAB_TEMPLATES: dict[str, list[dict]] = {
    "dr.nguyen.van.an@healthai.dev": [
        {
            "test_name": "Cardiac Troponin I + BNP Panel",
            "test_type": "blood_panel",
            "priority":  "urgent",
            "file_type": "manual",
            "ai_draft":  json.dumps([
                {"name": "Troponin I",  "value": "0.04", "unit": "ng/mL",   "flag": "normal", "reference_low": "0",    "reference_high": "0.04"},
                {"name": "BNP",         "value": "186",  "unit": "pg/mL",   "flag": "high",   "reference_low": "0",    "reference_high": "100"},
                {"name": "CK-MB",       "value": "4.2",  "unit": "ng/mL",   "flag": "normal", "reference_low": "0",    "reference_high": "5.0"},
                {"name": "D-dimer",     "value": "0.3",  "unit": "ug/mL",   "flag": "normal", "reference_low": "0",    "reference_high": "0.5"},
            ]),
            "notes": (
                "Routine cardiac checkup. Troponin I at upper limit (0.04), BNP elevated at 186 pg/mL — "
                "early ventricular stress. No acute MI pattern. Recommend serial ECG, repeat troponin at 6h, echocardiogram."
            ),
        },
        {
            "test_name": "12-Lead ECG Interpretation",
            "test_type": "ecg",
            "priority":  "urgent",
            "file_type": "manual",
            "ai_draft":  json.dumps([
                {"lead": "II,III,aVF", "finding": "Inverted P wave in lead III — possible ectopic atrial rhythm", "severity": "mild"},
                {"lead": "V1-V4",      "finding": "No ST elevation or depression",                                  "severity": "normal"},
                {"lead": "Rhythm",     "finding": "Regular 88 bpm. PR interval 0.18s (upper normal).",             "severity": "normal"},
                {"lead": "QTc",        "finding": "QTc 432 ms — within normal limits",                             "severity": "normal"},
            ]),
            "notes": (
                "Mildly prolonged PR interval (0.18s) with possible ectopic atrial beat in lead III. "
                "No acute ischemic changes. Correlate with elevated BNP."
            ),
        },
    ],
    "dr.tran.thi.bich@healthai.dev": [
        {
            "test_name": "Complete Blood Count + CRP + ESR",
            "test_type": "blood_panel",
            "priority":  "routine",
            "file_type": "manual",
            "ai_draft":  json.dumps([
                {"name": "Hemoglobin",  "value": "11.8", "unit": "g/dL",    "flag": "low",    "reference_low": "12.0", "reference_high": "16.0"},
                {"name": "WBC",         "value": "10.8", "unit": "10^3/uL", "flag": "high",   "reference_low": "4.5",  "reference_high": "10.5"},
                {"name": "Neutrophils", "value": "78",   "unit": "%",        "flag": "high",   "reference_low": "50",   "reference_high": "70"},
                {"name": "Lymphocytes", "value": "16",   "unit": "%",        "flag": "low",    "reference_low": "20",   "reference_high": "40"},
                {"name": "CRP",         "value": "32",   "unit": "mg/L",    "flag": "high",   "reference_low": "0",    "reference_high": "10"},
                {"name": "ESR",         "value": "48",   "unit": "mm/hr",   "flag": "high",   "reference_low": "0",    "reference_high": "20"},
                {"name": "Platelets",   "value": "315",  "unit": "10^3/uL", "flag": "normal"},
            ]),
            "notes": (
                "General medicine consultation. Leukocytosis with neutrophilia and elevated CRP (32) + ESR (48) "
                "indicate active inflammatory/infectious process. Mild anemia. Recommend: blood culture, urine analysis, chest X-ray."
            ),
        },
    ],
    "dr.le.minh.duc@healthai.dev": [
        {
            "test_name": "Anti-Epileptic Drug Levels + Ammonia",
            "test_type": "blood_panel",
            "priority":  "routine",
            "file_type": "manual",
            "ai_draft":  json.dumps([
                {"name": "Valproate (Depakine)", "value": "48",  "unit": "ug/mL", "flag": "low",    "reference_low": "50",  "reference_high": "100"},
                {"name": "Levetiracetam",        "value": "22",  "unit": "ug/mL", "flag": "normal", "reference_low": "12",  "reference_high": "46"},
                {"name": "ALT",                  "value": "35",  "unit": "U/L",   "flag": "normal"},
                {"name": "AST",                  "value": "30",  "unit": "U/L",   "flag": "normal"},
                {"name": "Ammonia",              "value": "52",  "unit": "ug/dL", "flag": "high",   "reference_low": "15",  "reference_high": "45"},
                {"name": "Sodium",               "value": "138", "unit": "mEq/L", "flag": "normal"},
            ]),
            "notes": (
                "Epilepsy medication review. Valproate sub-therapeutic (48, target 50-100) — increase dose by 250mg. "
                "Ammonia mildly elevated (52) — early valproate-induced hyperammonemia despite normal LFTs. Monitor closely."
            ),
        },
    ],
    "dr.pham.hong.van@healthai.dev": [
        {
            "test_name": "IgE Total + Eosinophil Count",
            "test_type": "blood_panel",
            "priority":  "routine",
            "file_type": "manual",
            "ai_draft":  json.dumps([
                {"name": "Total IgE",        "value": "485",  "unit": "IU/mL",   "flag": "high",   "reference_low": "0",   "reference_high": "100"},
                {"name": "Eosinophils",      "value": "8.2",  "unit": "%",        "flag": "high",   "reference_low": "0",   "reference_high": "5"},
                {"name": "Eosinophil (abs)", "value": "0.68", "unit": "10^3/uL", "flag": "high",   "reference_low": "0",   "reference_high": "0.5"},
                {"name": "WBC",              "value": "7.2",  "unit": "10^3/uL", "flag": "normal"},
                {"name": "CRP",              "value": "5",    "unit": "mg/L",    "flag": "normal"},
            ]),
            "notes": (
                "Eczema follow-up. Markedly elevated Total IgE (485) and peripheral eosinophilia confirm atopic diathesis. "
                "Consider dupilumab if topicals fail. Allergen avoidance reinforced."
            ),
        },
    ],
    "dr.vo.thanh.tung@healthai.dev": [
        {
            "test_name": "Post-Surgical Inflammatory Markers",
            "test_type": "blood_panel",
            "priority":  "routine",
            "file_type": "manual",
            "ai_draft":  json.dumps([
                {"name": "CRP",               "value": "18",  "unit": "mg/L",    "flag": "high",   "reference_low": "0",   "reference_high": "10"},
                {"name": "ESR",               "value": "42",  "unit": "mm/hr",   "flag": "high",   "reference_low": "0",   "reference_high": "20"},
                {"name": "WBC",               "value": "8.4", "unit": "10^3/uL", "flag": "normal"},
                {"name": "Serum Uric Acid",   "value": "7.8", "unit": "mg/dL",   "flag": "high",   "reference_low": "3.5", "reference_high": "7.2"},
                {"name": "Rheumatoid Factor", "value": "18",  "unit": "IU/mL",   "flag": "normal", "reference_low": "0",   "reference_high": "20"},
                {"name": "Anti-CCP",          "value": "12",  "unit": "U/mL",    "flag": "normal", "reference_low": "0",   "reference_high": "17"},
            ]),
            "notes": (
                "Post-surgery rehabilitation check. Mild residual inflammation (CRP 18, ESR 42) — expected post-op. "
                "Elevated uric acid (7.8) — low-purine diet. RF and anti-CCP negative. Continue physiotherapy, reassess 6w."
            ),
        },
    ],
    "dr.pham.thi.lan.huong@healthai.dev": [
        {
            "test_name": "Annual Spirometry + Pulse Oximetry",
            "test_type": "other",
            "priority":  "routine",
            "file_type": "manual",
            "ai_draft":  json.dumps([
                {"name": "FEV1",          "value": "55",   "unit": "%predicted", "flag": "low"},
                {"name": "FVC",           "value": "72",   "unit": "%predicted", "flag": "normal"},
                {"name": "FEV1/FVC",      "value": "0.60", "unit": "ratio",      "flag": "low"},
                {"name": "SpO2 (rest)",   "value": "94",   "unit": "%",          "flag": "low", "reference_low": "95", "reference_high": "100"},
                {"name": "SpO2 (effort)", "value": "88",   "unit": "%",          "flag": "low", "reference_low": "90", "reference_high": "100"},
                {"name": "DLCO",          "value": "48",   "unit": "%predicted", "flag": "low"},
            ]),
            "notes": (
                "Annual COPD checkup. FEV1 declined to 55% (was 58%) — mild progression. "
                "SpO2 drops to 88% on effort — exercise-induced hypoxemia. Consider ambulatory oxygen. "
                "GOLD Stage II-III borderline. Review inhaler technique, consider PDE4 inhibitor."
            ),
        },
    ],
    "dr.hoang.van.minh@healthai.dev": [
        {
            "test_name": "Comprehensive Renal Function Panel",
            "test_type": "blood_panel",
            "priority":  "routine",
            "file_type": "manual",
            "ai_draft":  json.dumps([
                {"name": "Creatinine",  "value": "2.4", "unit": "mg/dL",  "flag": "high", "reference_low": "0.6", "reference_high": "1.2"},
                {"name": "BUN",         "value": "44",  "unit": "mg/dL",  "flag": "high", "reference_low": "7",   "reference_high": "25"},
                {"name": "eGFR",        "value": "27",  "unit": "mL/min", "flag": "low",  "reference_low": "60",  "reference_high": "120"},
                {"name": "Potassium",   "value": "5.8", "unit": "mEq/L",  "flag": "high", "reference_low": "3.5", "reference_high": "5.1"},
                {"name": "Bicarbonate", "value": "18",  "unit": "mEq/L",  "flag": "low",  "reference_low": "22",  "reference_high": "29"},
                {"name": "Phosphorus",  "value": "5.4", "unit": "mg/dL",  "flag": "high", "reference_low": "2.5", "reference_high": "4.5"},
                {"name": "Hemoglobin",  "value": "9.8", "unit": "g/dL",   "flag": "low",  "reference_low": "12",  "reference_high": "16"},
            ]),
            "notes": (
                "Nephrology routine. CKD progressed — eGFR 27 (Stage 4, was 32). "
                "Hyperkalemia K+ 5.8 — restrict diet, consider polystyrene. "
                "Metabolic acidosis HCO3 18 — start NaHCO3. Hyperphosphatemia — phosphate binder. "
                "Anemia of CKD Hb 9.8 — consider ESA. Discuss AV fistula planning."
            ),
        },
    ],
    "dr.nguyen.thi.hue.linh@healthai.dev": [
        {
            "test_name": "CBC + Reticulocyte Count + Iron Studies",
            "test_type": "blood_panel",
            "priority":  "urgent",
            "file_type": "manual",
            "ai_draft":  json.dumps([
                {"name": "Hemoglobin",       "value": "7.4",  "unit": "g/dL",    "flag": "low",  "reference_low": "12",  "reference_high": "16"},
                {"name": "MCV",              "value": "64",   "unit": "fL",      "flag": "low",  "reference_low": "80",  "reference_high": "100"},
                {"name": "MCH",              "value": "20",   "unit": "pg",      "flag": "low",  "reference_low": "26",  "reference_high": "34"},
                {"name": "Reticulocytes",    "value": "0.8",  "unit": "%",       "flag": "low",  "reference_low": "0.5", "reference_high": "2.5"},
                {"name": "Serum Iron",       "value": "38",   "unit": "ug/dL",   "flag": "low",  "reference_low": "60",  "reference_high": "170"},
                {"name": "TIBC",             "value": "480",  "unit": "ug/dL",   "flag": "high", "reference_low": "240", "reference_high": "450"},
                {"name": "Transferrin Sat.", "value": "8",    "unit": "%",       "flag": "low",  "reference_low": "20",  "reference_high": "50"},
                {"name": "Ferritin",         "value": "4",    "unit": "ng/mL",   "flag": "low",  "reference_low": "12",  "reference_high": "150"},
                {"name": "WBC",              "value": "6.8",  "unit": "10^3/uL", "flag": "normal"},
                {"name": "Platelets",        "value": "195",  "unit": "10^3/uL", "flag": "normal"},
            ]),
            "notes": (
                "Hematology consultation. Severe iron deficiency anemia (Hb 7.4, ferritin 4, Tsat 8%). "
                "Low reticulocytes — inadequate marrow response. Recommend IV iron infusion + GI workup for occult blood loss."
            ),
        },
    ],
    "dr.tran.van.phuong@healthai.dev": [
        {
            "test_name": "HbA1c + Glucose + Insulin Resistance Panel",
            "test_type": "blood_panel",
            "priority":  "routine",
            "file_type": "manual",
            "ai_draft":  json.dumps([
                {"name": "HbA1c",            "value": "7.6",  "unit": "%",       "flag": "high",   "reference_low": "0",  "reference_high": "6.5"},
                {"name": "Fasting Glucose",  "value": "162",  "unit": "mg/dL",   "flag": "high",   "reference_low": "70", "reference_high": "100"},
                {"name": "2h Post-prandial", "value": "248",  "unit": "mg/dL",   "flag": "high",   "reference_low": "0",  "reference_high": "140"},
                {"name": "Fasting Insulin",  "value": "18",   "unit": "uIU/mL",  "flag": "high",   "reference_low": "2",  "reference_high": "15"},
                {"name": "HOMA-IR",          "value": "7.2",  "unit": "index",   "flag": "high",   "reference_low": "0",  "reference_high": "2.5"},
                {"name": "C-peptide",        "value": "2.8",  "unit": "ng/mL",   "flag": "normal"},
                {"name": "TSH",              "value": "2.1",  "unit": "mIU/L",   "flag": "normal"},
            ]),
            "notes": (
                "Endocrinology routine. HbA1c 7.6% — suboptimal (target <7%). "
                "HOMA-IR 7.2 confirms marked insulin resistance. Post-prandial glucose 248. "
                "C-peptide preserved — not T1DM. Consider GLP-1 agonist or acarbose. Intensify lifestyle intervention."
            ),
        },
    ],
}


# ── Seed function ─────────────────────────────────────────────────────────────

async def seed_emr_db(completed_appointments: list[dict], user_ids: dict[str, str], in_progress_appointments: list[dict] | None = None) -> None:
    """Insert lab orders + lab results per doctor (linked to completed appointments) and per patient (standalone)."""
    engine = create_async_engine(_emr_db_url(), echo=False)
    order_count = result_count = 0
    try:
        async with engine.begin() as conn:
            by_doctor: dict[str, list[dict]] = {}
            for appt in completed_appointments:
                by_doctor.setdefault(appt["doctor_email"], []).append(appt)

            # ── 1. Appointment-linked lab records (2 per doctor) ──────────────
            for doc_email, appts in by_doctor.items():
                doctor_id = user_ids[doc_email]
                # Idempotent re-run: clear existing seeded EMR data for this doctor
                await conn.execute(
                    text("DELETE FROM lab_results WHERE doctor_id = :did"), {"did": doctor_id}
                )
                await conn.execute(
                    text("DELETE FROM lab_orders WHERE doctor_id = :did"), {"did": doctor_id}
                )

                for idx, tmpl in enumerate(EMR_TEMPLATES.get(doc_email, [])):
                    if idx >= len(appts):
                        break
                    appt          = appts[idx]
                    patient_id    = appt["patient_user_id"]
                    appt_date_obj = date.fromisoformat(appt["date"])
                    ordered_ts    = datetime(appt_date_obj.year, appt_date_obj.month, appt_date_obj.day, 9, 0)
                    review_ts     = datetime(appt_date_obj.year, appt_date_obj.month, appt_date_obj.day, 14, 0)
                    is_published  = tmpl["status"] == "PUBLISHED"

                    order_id      = str(uuid.uuid4())
                    ai_draft_val  = tmpl["ai_draft"]
                    is_tabular    = isinstance(ai_draft_val, str) and ai_draft_val.startswith("[")
                    ai_visual_str = ai_draft_val if is_tabular else None
                    dept          = _specialty_to_dept(_doc_email_to_specialty(doc_email))

                    await conn.execute(
                        text("""
                            INSERT INTO lab_orders
                                (id, patient_id, doctor_id, appointment_id,
                                 test_name, test_type, department, priority,
                                 ordered_at, created_at)
                            VALUES
                                (:id, :pid, :did, :appt_id,
                                 :tname, :ttype, :dept, :pri,
                                 :ots, :ots)
                            ON CONFLICT (id) DO NOTHING
                        """),
                        {
                            "id": order_id, "pid": patient_id,
                            "did": doctor_id, "appt_id": appt["id"],
                            "tname": tmpl["test_name"],
                            "ttype": tmpl["test_type"].upper(),
                            "dept":  dept,
                            "pri":   tmpl["priority"].upper(),
                            "ots":   ordered_ts,
                        },
                    )
                    order_count += 1

                    result_id          = str(uuid.uuid4())
                    pub_findings_str   = ai_draft_val if is_tabular and is_published else None
                    await conn.execute(
                        text("""
                            INSERT INTO lab_results
                                (id, order_id, patient_id, doctor_id,
                                 file_type, status, ai_draft_text, ai_visual_findings,
                                 doctor_notes,
                                 verified_by, verified_at,
                                 published_text, published_findings, published_at,
                                 created_at)
                            VALUES
                                (:id, :oid, :pid, :did,
                                 :ftype, :status, :draft, CAST(:vis AS JSONB),
                                 :notes,
                                 :vby, :vat,
                                 :pub_text, CAST(:pub_find AS JSONB), :pub_at,
                                 :cat)
                            ON CONFLICT (id) DO NOTHING
                        """),
                        {
                            "id":       result_id,
                            "oid":      order_id,
                            "pid":      patient_id,
                            "did":      doctor_id,
                            "ftype":    tmpl["file_type"],
                            "status":   tmpl["status"],
                            "draft":    ai_draft_val if isinstance(ai_draft_val, str) else json.dumps(ai_draft_val),
                            "vis":      ai_visual_str,
                            "notes":    tmpl["notes"],
                            "vby":      doctor_id if is_published else None,
                            "vat":      review_ts  if is_published else None,
                            "pub_text": tmpl.get("pub_text") if is_published else None,
                            "pub_find": pub_findings_str,
                            "pub_at":   review_ts  if is_published else None,
                            "cat":      ordered_ts,
                        },
                    )
                    result_count += 1

            # ── 2. Standalone per-patient lab records (no appointment) ────────
            today = datetime.now()
            for patient_info in PATIENTS:
                p_email     = patient_info["email"]
                if p_email not in user_ids:
                    continue
                patient_id  = user_ids[p_email]
                doc_email   = patient_info.get("doctor_email", "")
                doctor_id   = user_ids.get(doc_email)
                if not doctor_id:
                    continue
                dept        = _specialty_to_dept(_doc_email_to_specialty(doc_email))
                templates   = PATIENT_LAB_TEMPLATES.get(p_email, [])
                for idx, tmpl in enumerate(templates):
                    ordered_ts   = today - timedelta(days=90 - idx * 20)
                    review_ts    = ordered_ts + timedelta(hours=5)
                    is_published = tmpl["status"] == "PUBLISHED"

                    order_id     = str(uuid.uuid4())
                    ai_draft_val = tmpl["ai_draft"]
                    is_tabular   = isinstance(ai_draft_val, str) and ai_draft_val.startswith("[")
                    ai_visual_str= ai_draft_val if is_tabular else None

                    await conn.execute(
                        text("""
                            INSERT INTO lab_orders
                                (id, patient_id, doctor_id, appointment_id,
                                 test_name, test_type, department, priority,
                                 ordered_at, created_at)
                            VALUES
                                (:id, :pid, :did, NULL,
                                 :tname, :ttype, :dept, :pri,
                                 :ots, :ots)
                            ON CONFLICT (id) DO NOTHING
                        """),
                        {
                            "id": order_id, "pid": patient_id, "did": doctor_id,
                            "tname": tmpl["test_name"],
                            "ttype": tmpl["test_type"].upper(),
                            "dept":  dept,
                            "pri":   tmpl["priority"].upper(),
                            "ots":   ordered_ts,
                        },
                    )
                    order_count += 1

                    pub_findings_str = ai_draft_val if is_tabular and is_published else None
                    await conn.execute(
                        text("""
                            INSERT INTO lab_results
                                (id, order_id, patient_id, doctor_id,
                                 file_type, status, ai_draft_text, ai_visual_findings,
                                 doctor_notes,
                                 verified_by, verified_at,
                                 published_text, published_findings, published_at,
                                 created_at)
                            VALUES
                                (:id, :oid, :pid, :did,
                                 :ftype, :status, :draft, CAST(:vis AS JSONB),
                                 :notes,
                                 :vby, :vat,
                                 :pub_text, CAST(:pub_find AS JSONB), :pub_at,
                                 :cat)
                            ON CONFLICT (id) DO NOTHING
                        """),
                        {
                            "id":       str(uuid.uuid4()),
                            "oid":      order_id,
                            "pid":      patient_id,
                            "did":      doctor_id,
                            "ftype":    tmpl["file_type"],
                            "status":   tmpl["status"],
                            "draft":    ai_draft_val if isinstance(ai_draft_val, str) else json.dumps(ai_draft_val),
                            "vis":      ai_visual_str,
                            "notes":    tmpl["notes"],
                            "vby":      doctor_id if is_published else None,
                            "vat":      review_ts  if is_published else None,
                            "pub_text": tmpl.get("pub_text") if is_published else None,
                            "pub_find": pub_findings_str,
                            "pub_at":   review_ts  if is_published else None,
                            "cat":      ordered_ts,
                        },
                    )
                    result_count += 1

            # ── 3. DOCTOR_REVIEW labs linked to today's IN_PROGRESS appointments ──
            for appt in (in_progress_appointments or []):
                doc_email  = appt["doctor_email"]
                doctor_id  = appt["doctor_id"]
                patient_id = appt["patient_user_id"]
                dept       = _specialty_to_dept(_doc_email_to_specialty(doc_email))
                tmpl_list  = IN_PROGRESS_LAB_TEMPLATES.get(doc_email, [])
                if not tmpl_list:
                    continue
                appt_date_obj = date.fromisoformat(appt["date"])
                ordered_ts    = datetime(appt_date_obj.year, appt_date_obj.month, appt_date_obj.day, 10, 15)

                for tmpl in tmpl_list:
                    order_id      = str(uuid.uuid4())
                    ai_draft_val  = tmpl["ai_draft"]
                    is_tabular    = isinstance(ai_draft_val, str) and ai_draft_val.startswith("[")
                    ai_visual_str = ai_draft_val if is_tabular else None

                    await conn.execute(
                        text("""
                            INSERT INTO lab_orders
                                (id, patient_id, doctor_id, appointment_id,
                                 test_name, test_type, department, priority,
                                 ordered_at, created_at)
                            VALUES
                                (:id, :pid, :did, :appt_id,
                                 :tname, :ttype, :dept, :pri,
                                 :ots, :ots)
                            ON CONFLICT (id) DO NOTHING
                        """),
                        {
                            "id": order_id, "pid": patient_id,
                            "did": doctor_id, "appt_id": appt["id"],
                            "tname": tmpl["test_name"],
                            "ttype": tmpl["test_type"].upper(),
                            "dept":  dept,
                            "pri":   tmpl["priority"].upper(),
                            "ots":   ordered_ts,
                        },
                    )
                    order_count += 1

                    result_id = str(uuid.uuid4())
                    await conn.execute(
                        text("""
                            INSERT INTO lab_results
                                (id, order_id, patient_id, doctor_id,
                                 file_type, status, ai_draft_text, ai_visual_findings,
                                 doctor_notes,
                                 verified_by, verified_at,
                                 published_text, published_findings, published_at,
                                 created_at)
                            VALUES
                                (:id, :oid, :pid, :did,
                                 :ftype, 'DOCTOR_REVIEW', :draft, CAST(:vis AS JSONB),
                                 :notes,
                                 NULL, NULL,
                                 NULL, NULL, NULL,
                                 :cat)
                            ON CONFLICT (id) DO NOTHING
                        """),
                        {
                            "id":    result_id,
                            "oid":   order_id,
                            "pid":   patient_id,
                            "did":   doctor_id,
                            "ftype": tmpl["file_type"],
                            "draft": ai_draft_val if isinstance(ai_draft_val, str) else json.dumps(ai_draft_val),
                            "vis":   ai_visual_str,
                            "notes": tmpl["notes"],
                            "cat":   ordered_ts,
                        },
                    )
                    result_count += 1

        print(f"  [emr] Seeded {order_count} lab orders + {result_count} lab results.")
    finally:
        await engine.dispose()

    # ── 4. Holistic summaries — separate connection so failure is non-fatal ──
    HOLISTIC_TEXT: dict[str, str] = {
        "dr.nguyen.van.an@healthai.dev": (
            "HOLISTIC LAB ANALYSIS — Cardiology Patient\n"
            "ECG and CBC both reviewed together. Normal sinus rhythm, QTc 428ms — no drug-induced QT risk. "
            "CBC fully within range; Hb 14.2 g/dL adequate, NLR 1.8 normal. No inflammatory signal on CBC to explain prior chest symptoms. "
            "Combined impression: Stable cardiovascular patient with no haematological or electrophysiological concern. "
            "Continue current antihypertensive regimen. Annual ECG and CBC. "
            "Priority: ROUTINE. Physician review required before any medication change."
        ),
        "dr.tran.thi.bich@healthai.dev": (
            "HOLISTIC LAB ANALYSIS — General Medicine Patient\n"
            "CBC follow-up reviewed alongside prior KUB plain film. CBC normal (Hb 13.8, CRP 3.2 — no inflammation). "
            "KUB unremarkable — no renal calculi, no bowel obstruction. "
            "Combined impression: No acute intra-abdominal or haematological pathology. Mild Hb decline from 14.2→13.8 — dietary assessment recommended. "
            "No further acute investigation required at this visit. Annual review planned."
        ),
        "dr.le.minh.duc@healthai.dev": (
            "HOLISTIC LAB ANALYSIS — Neurology Patient\n"
            "Skull X-ray and brain MRI protocol reviewed together. Skull X-ray normal — no fracture, sella turcica normal. "
            "MRI: no epileptogenic lesion, no mesial temporal sclerosis; mild frontal atrophy (age-related). "
            "Combined impression: No structural cause for seizures identified on imaging. EEG correlation essential for seizure classification. "
            "Current anticonvulsant therapy appropriate. Functional MRI if medically refractory after EEG review. Priority: HIGH."
        ),
        "dr.pham.hong.van@healthai.dev": (
            "HOLISTIC LAB ANALYSIS — Dermatology Patient\n"
            "Patch test and dermatoscopy results reviewed together. Latex allergy 3+ confirmed — all procedures must be latex-free. "
            "Nickel/Cobalt co-sensitization (2+/1+). Three pigmented skin lesions — all benign on dermatoscopy (ABCDE score 0). "
            "Combined impression: Contact allergy clearly documented; no malignant skin lesion. "
            "Written allergen avoidance card provided. Annual total body dermatoscopy mapping recommended. Priority: ROUTINE."
        ),
        "dr.vo.thanh.tung@healthai.dev": (
            "HOLISTIC LAB ANALYSIS — General Medicine / Orthopaedic Patient\n"
            "Liver function panel (mildly elevated ALT/GGT) and lipid profile (atherogenic dyslipidaemia) reviewed together. "
            "Transaminase elevation (ALT 52, GGT 68) combined with high TG 225 and low HDL 38 is consistent with metabolic syndrome / NAFLD. "
            "LDL 162 significantly above target — ASCVD risk high. Statin initiated. "
            "Combined impression: Metabolic syndrome cluster — weight management, Mediterranean diet, and hepatic ultrasound required. "
            "Statin therapy started. Repeat LFT + lipids in 8 weeks. Priority: HIGH."
        ),
        "dr.pham.thi.lan.huong@healthai.dev": (
            "HOLISTIC LAB ANALYSIS — Respiratory Patient\n"
            "Spirometry and sputum culture reviewed together (see prior visit records). "
            "Spirometry: FEV1/FVC 0.62 — obstructive pattern consistent with COPD GOLD II. "
            "Combined impression: Active COPD management appropriate. No acute infectious exacerbation on culture. "
            "Continue LABA + ICS inhaler. Smoking cessation counselling reinforced. Annual spirometry. Priority: ROUTINE."
        ),
        "dr.hoang.van.minh@healthai.dev": (
            "HOLISTIC LAB ANALYSIS — Nephrology Patient\n"
            "Renal function panel and urinalysis with ACR reviewed together. "
            "Creatinine elevated, eGFR reduced consistent with CKD Stage 3b. Urine ACR 420 mg/g — macroalbuminuria. RBC casts present. "
            "Combined impression: Active glomerulonephritis with nephritic-nephrotic overlap. Urgent biopsy arranged. "
            "ACE inhibitor maximised. Prednisolone bridge therapy started. Priority: CRITICAL — urgent follow-up within 48h."
        ),
        "dr.nguyen.thi.hue.linh@healthai.dev": (
            "HOLISTIC LAB ANALYSIS — Haematology Patient\n"
            "CBC + iron studies and peripheral blood film reviewed together. "
            "Severe iron deficiency anaemia: Hb 8.2, ferritin 6, transferrin sat 4.7%. Blood film confirms IDA (pencil cells, target cells, marked anisocytosis). "
            "Combined impression: IDA confirmed with GI blood loss as likely source (stool OB positive, colonoscopy arranged). "
            "IV iron (Ferinject 1g) administered. Colonoscopy within 2 weeks. Priority: HIGH."
        ),
        "dr.tran.van.phuong@healthai.dev": (
            "HOLISTIC LAB ANALYSIS — Endocrinology Patient\n"
            "KUB plain film and thyroid function panel + autoantibodies reviewed together. "
            "KUB unremarkable (no renal calculi — but CT KUB recommended if stone disease suspected). "
            "TFT: Overt hyperthyroidism — TSH 0.04, FT4 4.2, FT3 9.8; TRAb 6.8 IU/L confirms Graves' disease. "
            "Combined impression: Graves' disease driving systemic hyperthyroid state; no incidental renal stone on plain film but sensitivity limited. "
            "Carbimazole 30mg started. Propranolol for symptom control. Ophthalmology referral. Priority: HIGH."
        ),
    }

    by_doctor_appts: dict[str, list[dict]] = {}
    for appt in completed_appointments:
        by_doctor_appts.setdefault(appt["doctor_email"], []).append(appt)

    summary_count = 0
    engine2 = create_async_engine(_emr_db_url(), echo=False)
    try:
        async with engine2.begin() as conn2:
            for doc_email, appts in by_doctor_appts.items():
                if len(appts) < 2:
                    continue
                appt = appts[1]  # second completed appointment — has the PUBLISHED result
                holistic_text = HOLISTIC_TEXT.get(doc_email)
                if not holistic_text:
                    continue
                appt_date_obj = date.fromisoformat(appt["date"])
                created_ts = datetime(appt_date_obj.year, appt_date_obj.month, appt_date_obj.day, 15, 0)
                await conn2.execute(
                    text("""
                        INSERT INTO appointment_lab_summaries
                            (id, appointment_id, patient_id, status,
                             ai_holistic_text, total_results,
                             created_at, updated_at)
                        VALUES
                            (:id, :appt_id, :pid, 'DONE',
                             :holistic, 2,
                             :cat, :cat)
                        ON CONFLICT (appointment_id) DO UPDATE
                            SET status = 'DONE',
                                ai_holistic_text = EXCLUDED.ai_holistic_text,
                                updated_at = NOW()
                    """),
                    {
                        "id":       str(uuid.uuid4()),
                        "appt_id": appt["id"],
                        "pid":     appt["patient_user_id"],
                        "holistic": holistic_text,
                        "cat":     created_ts,
                    },
                )
                summary_count += 1
        print(f"  [emr] Seeded {summary_count} holistic appointment summaries (DONE).")
    except Exception as exc:
        print(f"  [emr] WARNING: Could not seed appointment_lab_summaries (migration may be pending): {exc}")
    finally:
        await engine2.dispose()
