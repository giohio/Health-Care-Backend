"""Seed clinical DB — diagnoses, medications, clinical notes per patient."""
import uuid
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from .db_urls import _clinical_db_url
from .patients import PATIENTS

# ── Clinical templates keyed by patient email ────────────────────────────────
# Structured to give the AI Medical Summary rich context for each patient.

_today    = date.today()
_d30      = _today - timedelta(days=30)
_d60      = _today - timedelta(days=60)
_d90      = _today - timedelta(days=90)
_d180     = _today - timedelta(days=180)
_d365     = _today - timedelta(days=365)

CLINICAL_TEMPLATES: dict[str, dict] = {
    # ── Cardiology ────────────────────────────────────────────────────────────
    "patient.le.thi.mai@healthai.dev": {
        "diagnoses": [
            {
                "icd10": "I10", "name": "Essential Hypertension", "detail": "Stage 1 hypertension, well-controlled on medication",
                "severity": "moderate", "status": "chronic", "date": _d365,
            },
        ],
        "medications": [
            {"drug": "Amlodipine", "dosage": "5mg", "freq": "once daily", "route": "oral", "start": _d365, "status": "active",
             "notes": "For blood pressure control"},
            {"drug": "Aspirin", "dosage": "81mg", "freq": "once daily", "route": "oral", "start": _d180, "status": "active",
             "notes": "Antiplatelet therapy — patient is NOT allergic to low-dose aspirin"},
        ],
        "notes": [
            {"type": "soap", "content": "S: Patient reports occasional mild headaches, especially in the morning. No chest pain, no dyspnea.\nO: BP 138/88 mmHg, HR 76 bpm, SpO2 98%. Heart sounds normal.\nA: Essential hypertension, moderately controlled. Possible morning surge.\nP: Increase Amlodipine to 10mg if BP remains >140/90 on next visit. Advise low-sodium diet.", "ai": False},
            {"type": "progress", "content": "Follow-up visit: BP improved to 130/82 mmHg after dietary modification. Medication compliance confirmed. Continue current regimen.", "ai": False},
        ],
    },
    "patient.tran.van.long@healthai.dev": {
        "diagnoses": [
            {
                "icd10": "E11", "name": "Type 2 Diabetes Mellitus", "detail": "HbA1c 8.2%, poorly controlled",
                "severity": "moderate", "status": "chronic", "date": _d365,
            },
            {
                "icd10": "I10", "name": "Essential Hypertension", "detail": "Hypertension comorbid with diabetes",
                "severity": "moderate", "status": "chronic", "date": _d365,
            },
        ],
        "medications": [
            {"drug": "Metformin", "dosage": "1000mg", "freq": "twice daily with meals", "route": "oral", "start": _d365, "status": "active",
             "notes": "First-line diabetes treatment"},
            {"drug": "Glipizide", "dosage": "5mg", "freq": "once daily before breakfast", "route": "oral", "start": _d180, "status": "active",
             "notes": "Added for better glucose control"},
            {"drug": "Lisinopril", "dosage": "10mg", "freq": "once daily", "route": "oral", "start": _d365, "status": "active",
             "notes": "ACE inhibitor for hypertension and renal protection"},
        ],
        "notes": [
            {"type": "soap", "content": "S: Patient reports increased thirst, polyuria, and fatigue over past 2 weeks. Fasting glucose at home 180-220 mg/dL.\nO: BP 148/92 mmHg, HR 82 bpm. Random glucose 210 mg/dL. Weight 75 kg (BMI 25.4).\nA: Type 2 DM poorly controlled. Hypertension suboptimally managed.\nP: Increase Metformin to 1000mg BD. Add Glipizide 5mg. Repeat HbA1c in 3 months. Nutritionist referral.", "ai": False},
        ],
    },
    "patient.vo.thi.hoa@healthai.dev": {
        "diagnoses": [],
        "medications": [],
        "notes": [
            {"type": "progress", "content": "Routine annual check-up. No chronic conditions. Patient reports mild seasonal allergic rhinitis. Advised antihistamine as needed. All vitals normal.", "ai": False},
        ],
    },
    # ── Neurology ─────────────────────────────────────────────────────────────
    "patient.hoang.thi.thu@healthai.dev": {
        "diagnoses": [
            {
                "icd10": "G43.9", "name": "Migraine without aura", "detail": "Episodic migraines 2-3x per month, triggered by stress and bright lights",
                "severity": "moderate", "status": "chronic", "date": _d180,
            },
        ],
        "medications": [
            {"drug": "Sumatriptan", "dosage": "50mg", "freq": "as needed for acute migraine", "route": "oral", "start": _d180, "status": "active",
             "notes": "Abortive therapy for acute migraine attacks"},
            {"drug": "Propranolol", "dosage": "40mg", "freq": "twice daily", "route": "oral", "start": _d90, "status": "active",
             "notes": "Migraine prophylaxis"},
        ],
        "notes": [
            {"type": "soap", "content": "S: Patient reports 3 migraine episodes last month, each lasting 6-18 hours. Nausea and photophobia present. Sumatriptan effective.\nO: Neurological exam normal. BP 118/76 mmHg.\nA: Migraine without aura — moderate frequency. Prophylaxis indicated.\nP: Start Propranolol 40mg BD for prevention. Continue Sumatriptan PRN. Migraine diary recommended.", "ai": False},
        ],
    },
    "patient.bui.van.duc@healthai.dev": {
        "diagnoses": [
            {
                "icd10": "G40.9", "name": "Epilepsy, unspecified", "detail": "Generalized tonic-clonic seizures, last episode 6 months ago",
                "severity": "moderate", "status": "chronic", "date": _d365,
            },
        ],
        "medications": [
            {"drug": "Valproic acid", "dosage": "500mg", "freq": "twice daily", "route": "oral", "start": _d365, "status": "active",
             "notes": "Anti-epileptic — serum level 65 mcg/mL (therapeutic)"},
            {"drug": "Levetiracetam", "dosage": "500mg", "freq": "twice daily", "route": "oral", "start": _d180, "status": "active",
             "notes": "Add-on therapy for breakthrough seizures"},
        ],
        "notes": [
            {"type": "soap", "content": "S: No seizure in past 6 months. Patient reports mild cognitive slowing. Compliance good.\nO: Neurological exam normal. Valproate level 65 mcg/mL. Liver enzymes normal.\nA: Epilepsy well-controlled on dual therapy.\nP: Maintain current regimen. Annual EEG scheduled. Advise against driving until 12 months seizure-free.", "ai": False},
        ],
    },
    "patient.ly.thi.tuyet@healthai.dev": {
        "diagnoses": [
            {
                "icd10": "G44.2", "name": "Tension-type headache, chronic", "detail": "Daily headache >15 days/month for >3 months",
                "severity": "mild", "status": "chronic", "date": _d90,
            },
        ],
        "medications": [
            {"drug": "Amitriptyline", "dosage": "10mg", "freq": "once daily at night", "route": "oral", "start": _d90, "status": "active",
             "notes": "Low-dose for chronic headache prevention"},
            {"drug": "Paracetamol", "dosage": "500mg", "freq": "as needed, max 3g/day", "route": "oral", "start": _d90, "status": "active",
             "notes": "Acute headache relief — avoid overuse"},
        ],
        "notes": [
            {"type": "soap", "content": "S: Daily headache described as bilateral pressure sensation, 4/10 severity. No nausea, photophobia, or aura. Worsens with stress.\nO: Neurological exam normal. No papilledema.\nA: Chronic tension-type headache. Ibuprofen avoided due to allergy.\nP: Start Amitriptyline 10mg nocte. Paracetamol PRN. Stress management counseling.", "ai": False},
        ],
    },
    # ── Dermatology ───────────────────────────────────────────────────────────
    "patient.duong.van.khanh@healthai.dev": {
        "diagnoses": [
            {
                "icd10": "L20.9", "name": "Atopic Dermatitis (Eczema)", "detail": "Moderate eczema affecting arms and trunk, flaring seasonally",
                "severity": "moderate", "status": "chronic", "date": _d365,
            },
        ],
        "medications": [
            {"drug": "Triamcinolone acetonide cream 0.1%", "dosage": "apply thin layer", "freq": "twice daily to affected areas", "route": "topical", "start": _d30, "status": "active",
             "notes": "For active flare — avoid prolonged use on face"},
            {"drug": "Cetirizine", "dosage": "10mg", "freq": "once daily at night", "route": "oral", "start": _d90, "status": "active",
             "notes": "Antihistamine for itch control"},
            {"drug": "Emollient moisturizer", "dosage": "apply liberally", "freq": "3 times daily", "route": "topical", "start": _d365, "status": "active",
             "notes": "Skin barrier maintenance"},
        ],
        "notes": [
            {"type": "soap", "content": "S: Patient reports worsening itch and redness on both forearms over past 2 weeks. Using emollient regularly.\nO: Erythematous papules and excoriations on bilateral forearms, mild lichenification. No secondary infection signs.\nA: Atopic dermatitis, moderate flare. Latex contact should be avoided.\nP: Triamcinolone 0.1% BD for 2 weeks. Wet wrap therapy at home. Review in 4 weeks.", "ai": False},
        ],
    },
    "patient.ngo.thi.xuan@healthai.dev": {
        "diagnoses": [
            {
                "icd10": "L40.0", "name": "Psoriasis vulgaris", "detail": "Plaque psoriasis on elbows, knees, and scalp — PASI 12",
                "severity": "moderate", "status": "chronic", "date": _d180,
            },
        ],
        "medications": [
            {"drug": "Calcipotriol/Betamethasone dipropionate (Dovobet) ointment", "dosage": "apply once daily", "freq": "once daily", "route": "topical", "start": _d60, "status": "active",
             "notes": "First-line for plaque psoriasis"},
            {"drug": "Coal tar shampoo 2%", "dosage": "use 3x/week", "freq": "3 times per week", "route": "topical", "start": _d60, "status": "active",
             "notes": "For scalp psoriasis"},
        ],
        "notes": [
            {"type": "soap", "content": "S: Psoriasis plaques worsening over past month, possibly stress-triggered. Itching 6/10.\nO: Silvery scaly plaques on bilateral elbows, knees, and posterior scalp. PASI 12. No joint involvement.\nA: Moderate plaque psoriasis. No psoriatic arthritis signs.\nP: Dovobet ointment OD. Coal tar shampoo 3x/week. Consider phototherapy if no improvement in 8 weeks.", "ai": False},
        ],
    },
    "patient.trinh.van.hung@healthai.dev": {
        "diagnoses": [
            {
                "icd10": "L70.0", "name": "Acne vulgaris", "detail": "Moderate acne — comedonal and inflammatory papules on face and back",
                "severity": "mild", "status": "active", "date": _d90,
            },
        ],
        "medications": [
            {"drug": "Adapalene 0.1% gel", "dosage": "pea-sized amount", "freq": "once daily at night", "route": "topical", "start": _d90, "status": "active",
             "notes": "Retinoid for acne — use sunscreen"},
            {"drug": "Clindamycin 1% lotion", "dosage": "apply to face", "freq": "twice daily", "route": "topical", "start": _d90, "status": "active",
             "notes": "Antibiotic for inflammatory lesions — avoid systemic sulfa drugs (patient allergic)"},
            {"drug": "Benzoyl peroxide 5% wash", "dosage": "use as face wash", "freq": "once daily", "route": "topical", "start": _d90, "status": "active",
             "notes": "Reduces bacterial load"},
        ],
        "notes": [
            {"type": "progress", "content": "4-week follow-up: 30% reduction in inflammatory lesions. Patient using sunscreen. No adverse effects. Continue regimen.", "ai": False},
        ],
    },
    # ── Respiratory ───────────────────────────────────────────────────────────
    "patient.pham.van.khang@healthai.dev": {
        "diagnoses": [
            {
                "icd10": "J44.1", "name": "COPD with acute exacerbation", "detail": "GOLD Stage II COPD — FEV1 58% predicted",
                "severity": "moderate", "status": "chronic", "date": _d365,
            },
            {
                "icd10": "I10", "name": "Essential Hypertension", "detail": "BP controlled on Amlodipine",
                "severity": "mild", "status": "chronic", "date": _d365,
            },
        ],
        "medications": [
            {"drug": "Tiotropium (Spiriva)", "dosage": "18mcg", "freq": "once daily via HandiHaler", "route": "inhaled", "start": _d365, "status": "active",
             "notes": "LAMA bronchodilator for COPD maintenance"},
            {"drug": "Salmeterol/Fluticasone (Seretide) 50/250", "dosage": "1 puff", "freq": "twice daily", "route": "inhaled", "start": _d180, "status": "active",
             "notes": "LABA/ICS combination for COPD"},
            {"drug": "Salbutamol (Ventolin) 100mcg", "dosage": "2 puffs", "freq": "as needed for breathlessness", "route": "inhaled", "start": _d365, "status": "active",
             "notes": "Rescue inhaler — SABA"},
            {"drug": "Amlodipine", "dosage": "5mg", "freq": "once daily", "route": "oral", "start": _d365, "status": "active",
             "notes": "Calcium channel blocker for hypertension"},
        ],
        "notes": [
            {"type": "soap", "content": "S: Increased dyspnea for 5 days, productive cough with yellow-green sputum, no fever.\nO: RR 22, SpO2 92% on room air, HR 98. Bilateral rhonchi. T 37.2°C.\nA: COPD acute exacerbation — possible bacterial trigger.\nP: Prednisolone 40mg x5 days. Doxycycline 100mg BD x7 days. Increase rescue inhaler use. Review in 1 week.", "ai": False},
        ],
    },
    "patient.luu.thi.mai@healthai.dev": {
        "diagnoses": [
            {
                "icd10": "J45.1", "name": "Allergic asthma, moderate persistent", "detail": "Asthma triggered by dust mites, seasonal",
                "severity": "moderate", "status": "chronic", "date": _d365,
            },
        ],
        "medications": [
            {"drug": "Budesonide/Formoterol (Symbicort) 160/4.5", "dosage": "2 puffs", "freq": "twice daily", "route": "inhaled", "start": _d365, "status": "active",
             "notes": "ICS/LABA for asthma maintenance"},
            {"drug": "Salbutamol (Ventolin)", "dosage": "2 puffs 100mcg", "freq": "as needed for acute wheeze", "route": "inhaled", "start": _d365, "status": "active",
             "notes": "Rescue bronchodilator"},
            {"drug": "Cetirizine", "dosage": "10mg", "freq": "once daily", "route": "oral", "start": _d180, "status": "active",
             "notes": "For dust mite allergy symptoms"},
        ],
        "notes": [
            {"type": "soap", "content": "S: Waking up 2-3x per week with wheeze. Daytime symptoms most days. Using rescue inhaler daily.\nO: Mild bilateral wheeze. PEFR 68% predicted. SpO2 97%.\nA: Moderate persistent asthma — poorly controlled. Step-up therapy indicated.\nP: Upgrade to Symbicort 160/4.5 BD. HEPA filter for bedroom. Allergen avoidance education.", "ai": False},
        ],
    },
    # ── Nephrology ────────────────────────────────────────────────────────────
    "patient.dinh.thi.lan@healthai.dev": {
        "diagnoses": [
            {
                "icd10": "N18.3", "name": "Chronic Kidney Disease Stage 3", "detail": "eGFR 35 mL/min, secondary to diabetes and hypertension",
                "severity": "moderate", "status": "chronic", "date": _d365,
            },
            {
                "icd10": "E11", "name": "Type 2 Diabetes Mellitus", "detail": "Diabetic nephropathy contributing to CKD",
                "severity": "moderate", "status": "chronic", "date": _d365,
            },
        ],
        "medications": [
            {"drug": "Lisinopril", "dosage": "10mg", "freq": "once daily", "route": "oral", "start": _d365, "status": "active",
             "notes": "ACE inhibitor — nephroprotective, BP control"},
            {"drug": "Insulin glargine (Lantus)", "dosage": "20 units", "freq": "once daily at night", "route": "subcutaneous", "start": _d180, "status": "active",
             "notes": "Basal insulin for diabetes in CKD"},
            {"drug": "Sodium bicarbonate", "dosage": "500mg", "freq": "three times daily", "route": "oral", "start": _d90, "status": "active",
             "notes": "For metabolic acidosis in CKD"},
            {"drug": "Erythropoietin (EPO) 4000 IU", "dosage": "4000 IU", "freq": "weekly subcutaneous", "route": "subcutaneous", "start": _d60, "status": "active",
             "notes": "For CKD-related anemia (Hb 9.8 g/dL)"},
        ],
        "notes": [
            {"type": "soap", "content": "S: Fatigue, mild ankle swelling, reduced urine output. No chest pain, no fever.\nO: BP 152/96, HR 80, SpO2 97%. Bilateral pitting edema 1+. Creatinine 2.4 mg/dL, eGFR 32.\nA: CKD Stage 3 progressing. Diabetes and hypertension poorly controlled.\nP: Increase Lisinopril to 20mg. Start EPO 4000 IU weekly. Dietary protein restriction 0.6g/kg/day. Nephrology follow-up every 3 months.", "ai": False},
        ],
    },
    "patient.le.van.son@healthai.dev": {
        "diagnoses": [
            {
                "icd10": "N18.4", "name": "Chronic Kidney Disease Stage 4", "detail": "eGFR 22 mL/min, approaching ESRD. Dialysis planning initiated.",
                "severity": "severe", "status": "chronic", "date": _d365,
            },
            {
                "icd10": "I10", "name": "Essential Hypertension", "detail": "Poorly controlled, BP often >160/100",
                "severity": "severe", "status": "chronic", "date": _d365,
            },
        ],
        "medications": [
            {"drug": "Amlodipine", "dosage": "10mg", "freq": "once daily", "route": "oral", "start": _d365, "status": "active",
             "notes": "Calcium channel blocker"},
            {"drug": "Furosemide", "dosage": "40mg", "freq": "twice daily", "route": "oral", "start": _d180, "status": "active",
             "notes": "Loop diuretic for fluid overload"},
            {"drug": "Calcium carbonate", "dosage": "500mg", "freq": "three times daily with meals", "route": "oral", "start": _d90, "status": "active",
             "notes": "Phosphate binder for CKD hyperphosphatemia"},
            {"drug": "Alfacalcidol", "dosage": "0.25 mcg", "freq": "once daily", "route": "oral", "start": _d90, "status": "active",
             "notes": "Active vitamin D for renal osteodystrophy"},
        ],
        "notes": [
            {"type": "soap", "content": "S: Progressive shortness of breath, lower limb edema worsening. Nausea, reduced appetite. Urine output <600 mL/day.\nO: BP 168/102, HR 88. Bilateral crackles at lung bases. 2+ pitting edema. Creatinine 4.2 mg/dL, eGFR 18.\nA: CKD Stage 4 rapidly progressing. Uremic symptoms emerging.\nP: AV fistula referral for haemodialysis access. Furosemide increased. Nephrology urgent review. Palliative care counseling offered.", "ai": False},
        ],
    },
    # ── Hematology ────────────────────────────────────────────────────────────
    "patient.vu.thi.hang@healthai.dev": {
        "diagnoses": [
            {
                "icd10": "D50.9", "name": "Iron Deficiency Anemia", "detail": "Hb 8.2 g/dL, Ferritin 6 ng/mL, MCV 68 fL. Dietary cause.",
                "severity": "moderate", "status": "active", "date": _d30,
            },
        ],
        "medications": [
            {"drug": "Ferrous sulfate", "dosage": "325mg", "freq": "twice daily on empty stomach", "route": "oral", "start": _d30, "status": "active",
             "notes": "Iron supplementation — take with Vitamin C for absorption"},
            {"drug": "Vitamin C", "dosage": "500mg", "freq": "twice daily with iron", "route": "oral", "start": _d30, "status": "active",
             "notes": "Enhances iron absorption"},
            {"drug": "Folic acid", "dosage": "5mg", "freq": "once daily", "route": "oral", "start": _d30, "status": "active",
             "notes": "Supportive"},
        ],
        "notes": [
            {"type": "soap", "content": "S: Fatigue, pallor, mild dyspnea on exertion, cold intolerance. Menorrhagia history.\nO: Pale conjunctivae, HR 98, BP 106/68. Hb 8.2, MCV 68, ferritin 6.\nA: Iron deficiency anemia, moderate severity.\nP: Ferrous sulfate 325mg BD + Vit C. Gynecology referral for menorrhagia. Recheck CBC in 6 weeks.", "ai": False},
        ],
    },
    "patient.phan.van.thanh@healthai.dev": {
        "diagnoses": [
            {
                "icd10": "C91.1", "name": "Chronic Lymphocytic Leukemia (CLL)", "detail": "Rai Stage II, Binet B. Watchful waiting — no treatment indication yet.",
                "severity": "severe", "status": "chronic", "date": _d365,
            },
        ],
        "medications": [
            {"drug": "Acyclovir", "dosage": "400mg", "freq": "twice daily", "route": "oral", "start": _d180, "status": "active",
             "notes": "HSV prophylaxis in immunocompromised patient"},
            {"drug": "Trimethoprim-sulfamethoxazole (Co-trimoxazole)", "dosage": "960mg", "freq": "three times per week", "route": "oral", "start": _d180, "status": "active",
             "notes": "PCP prophylaxis"},
        ],
        "notes": [
            {"type": "soap", "content": "S: Mild fatigue. No B-symptoms (no fever, night sweats, weight loss). No infections.\nO: Bilateral cervical lymphadenopathy (2cm). Spleen tip palpable. WBC 42,000/μL, lymphocytes 85%.\nA: CLL Rai Stage II. Stable, no treatment indication. Continue monitoring.\nP: CBC and lymph node exam every 3 months. Opportunistic infection prophylaxis. Annual flu + pneumococcal vaccine.", "ai": False},
        ],
    },
    # ── Endocrinology ─────────────────────────────────────────────────────────
    "patient.bui.thi.linh@healthai.dev": {
        "diagnoses": [
            {
                "icd10": "E11", "name": "Type 2 Diabetes Mellitus", "detail": "HbA1c 9.1%, on insulin",
                "severity": "severe", "status": "chronic", "date": _d365,
            },
            {
                "icd10": "I10", "name": "Essential Hypertension", "detail": "BP 152/96 on dual therapy",
                "severity": "moderate", "status": "chronic", "date": _d365,
            },
            {
                "icd10": "E66.0", "name": "Obesity, Class II", "detail": "BMI 27.3, abdominal adiposity",
                "severity": "moderate", "status": "chronic", "date": _d365,
            },
        ],
        "medications": [
            {"drug": "Insulin glargine (Lantus)", "dosage": "24 units", "freq": "once daily at bedtime", "route": "subcutaneous", "start": _d365, "status": "active",
             "notes": "Basal insulin — titrate by 2 units every 3 days if fasting glucose >130"},
            {"drug": "Insulin lispro (Humalog)", "dosage": "6-8 units", "freq": "before each main meal", "route": "subcutaneous", "start": _d180, "status": "active",
             "notes": "Bolus insulin — adjust per carbohydrate content"},
            {"drug": "Metformin", "dosage": "500mg", "freq": "twice daily", "route": "oral", "start": _d365, "status": "active",
             "notes": "Insulin sensitizer — keep for cardiovascular benefit"},
            {"drug": "Amlodipine", "dosage": "10mg", "freq": "once daily", "route": "oral", "start": _d365, "status": "active",
             "notes": "CCB for hypertension"},
            {"drug": "Losartan", "dosage": "50mg", "freq": "once daily", "route": "oral", "start": _d180, "status": "active",
             "notes": "ARB for hypertension and renal protection"},
        ],
        "notes": [
            {"type": "soap", "content": "S: Polyuria, polydipsia, blurred vision. Fasting glucose 180-240 at home. BP readings 140-160 systolic.\nO: BP 158/98, HR 84. Weight 68 kg, BMI 27.3. HbA1c 9.1%. Fundoscopy: mild background retinopathy.\nA: Type 2 DM severely uncontrolled. Hypertension not at target. Early diabetic retinopathy.\nP: Add bolus insulin. Ophthalmology referral. Dietitian for structured meal plan. Target HbA1c <7%.", "ai": False},
        ],
    },
    "patient.do.van.hung@healthai.dev": {
        "diagnoses": [
            {
                "icd10": "E03.9", "name": "Hypothyroidism, unspecified", "detail": "TSH 8.2 mIU/L, Free T4 0.6 ng/dL — on replacement therapy",
                "severity": "mild", "status": "chronic", "date": _d365,
            },
            {
                "icd10": "E78.5", "name": "Hyperlipidemia (Dyslipidemia)", "detail": "Total cholesterol 248 mg/dL, LDL 168 mg/dL",
                "severity": "moderate", "status": "chronic", "date": _d365,
            },
        ],
        "medications": [
            {"drug": "Levothyroxine (T4)", "dosage": "75 mcg", "freq": "once daily 30 minutes before breakfast", "route": "oral", "start": _d365, "status": "active",
             "notes": "Thyroid hormone replacement — take on empty stomach"},
            {"drug": "Atorvastatin", "dosage": "40mg", "freq": "once daily at night", "route": "oral", "start": _d180, "status": "active",
             "notes": "Statin for dyslipidemia"},
        ],
        "notes": [
            {"type": "soap", "content": "S: Fatigue improving on Levothyroxine. Cold intolerance still present. Constipation.\nO: HR 62, BP 128/82. Weight 82 kg. TSH 3.8 (improving). Free T4 0.9 ng/dL.\nA: Hypothyroidism responding to treatment. Dyslipidemia — statin initiated.\nP: Continue Levothyroxine 75mcg. Recheck thyroid panel in 6 weeks. Statin initiated — check LFTs in 3 months.", "ai": False},
        ],
    },
    "patient.truong.thi.mai@healthai.dev": {
        "diagnoses": [
            {
                "icd10": "E05.9", "name": "Hyperthyroidism, unspecified", "detail": "TSH 0.4 mIU/L, Free T4 3.2 ng/dL, Free T3 7.5 pg/mL — Graves disease suspected",
                "severity": "moderate", "status": "active", "date": _d30,
            },
        ],
        "medications": [
            {"drug": "Carbimazole", "dosage": "30mg", "freq": "once daily for 4 weeks then titrate", "route": "oral", "start": _d30, "status": "active",
             "notes": "Anti-thyroid drug — monitor CBC for agranulocytosis"},
            {"drug": "Propranolol", "dosage": "40mg", "freq": "three times daily", "route": "oral", "start": _d30, "status": "active",
             "notes": "For sympathomimetic symptoms (tremor, palpitations)"},
        ],
        "notes": [
            {"type": "soap", "content": "S: Palpitations, heat intolerance, weight loss 4 kg in 2 months, anxiety, hand tremor.\nO: HR 112, BP 134/78, thyroid goitre (grade II), fine tremor, warm moist skin.\nA: Hyperthyroidism — Graves disease most likely. TRAb pending.\nP: Carbimazole 30mg daily. Propranolol for symptomatic relief. Endocrinology urgent referral. Ophthalmology screening for orbitopathy.", "ai": False},
        ],
    },
    # ── General Medicine (Dr. Tran Thi Bich) ─────────────────────────────────
    "patient.nguyen.van.minh@healthai.dev": {
        "diagnoses": [
            {
                "icd10": "J45.0", "name": "Allergic Asthma (mild intermittent)", "detail": "Triggered by dust mites, well-controlled on low-dose ICS",
                "severity": "mild", "status": "chronic", "date": _d365,
            },
        ],
        "medications": [
            {"drug": "Budesonide 100mcg inhaler", "dosage": "1 puff", "freq": "once daily", "route": "inhaled", "start": _d365, "status": "active",
             "notes": "Preventive ICS — paediatric dose"},
            {"drug": "Salbutamol syrup 2mg/5mL", "dosage": "5 mL", "freq": "as needed up to 3x daily", "route": "oral", "start": _d365, "status": "active",
             "notes": "Rescue bronchodilator for child"},
        ],
        "notes": [
            {"type": "progress", "content": "Child's asthma well-controlled. No nocturnal symptoms. PEFR 85% predicted. Growth normal on paediatric height chart. Continue current regimen. Review in 3 months.", "ai": False},
        ],
    },
    # ── General Medicine (Dr. Vo Thanh Tung) ─────────────────────────────────
    "patient.mai.thi.lien@healthai.dev": {
        "diagnoses": [
            {
                "icd10": "M19.90", "name": "Osteoarthritis", "detail": "Bilateral knee osteoarthritis — Kellgren-Lawrence Grade II",
                "severity": "moderate", "status": "chronic", "date": _d365,
            },
        ],
        "medications": [
            {"drug": "Celecoxib", "dosage": "200mg", "freq": "once daily with food", "route": "oral", "start": _d180, "status": "active",
             "notes": "COX-2 inhibitor for joint pain — safer GI profile"},
            {"drug": "Glucosamine sulfate", "dosage": "1500mg", "freq": "once daily", "route": "oral", "start": _d365, "status": "active",
             "notes": "Joint supplement"},
            {"drug": "Diclofenac 1% gel", "dosage": "apply 2-4g", "freq": "3-4 times daily to affected joint", "route": "topical", "start": _d90, "status": "active",
             "notes": "Topical NSAID for local pain relief"},
        ],
        "notes": [
            {"type": "soap", "content": "S: Bilateral knee pain 5/10, worse going down stairs and after prolonged sitting. Morning stiffness <30 minutes.\nO: Crepitus bilateral knees, mild effusion right knee. ROM slightly reduced. X-ray: joint space narrowing, osteophytes.\nA: Osteoarthritis bilateral knees, moderate.\nP: Celecoxib 200mg OD. Physiotherapy referral. Weight reduction goal: -5 kg. Swimming/cycling recommended.", "ai": False},
        ],
    },
    "patient.cao.van.toan@healthai.dev": {
        "diagnoses": [
            {
                "icd10": "M06.9", "name": "Rheumatoid Arthritis", "detail": "Seropositive RA — RF+, anti-CCP+. DAS28 score 4.2 (moderate activity)",
                "severity": "moderate", "status": "chronic", "date": _d365,
            },
            {
                "icd10": "M81.0", "name": "Osteoporosis", "detail": "T-score -2.8 at lumbar spine",
                "severity": "moderate", "status": "chronic", "date": _d365,
            },
        ],
        "medications": [
            {"drug": "Methotrexate", "dosage": "15mg", "freq": "once weekly", "route": "oral", "start": _d365, "status": "active",
             "notes": "DMARD for RA — take with folic acid"},
            {"drug": "Folic acid", "dosage": "5mg", "freq": "once daily (not on MTX day)", "route": "oral", "start": _d365, "status": "active",
             "notes": "To reduce MTX side effects"},
            {"drug": "Prednisolone", "dosage": "5mg", "freq": "once daily (bridge therapy)", "route": "oral", "start": _d60, "status": "active",
             "notes": "Short-term bridge — taper in 8 weeks"},
            {"drug": "Alendronate", "dosage": "70mg", "freq": "once weekly on empty stomach", "route": "oral", "start": _d180, "status": "active",
             "notes": "Bisphosphonate for osteoporosis"},
            {"drug": "Calcium + Vitamin D3", "dosage": "1000mg/800 IU", "freq": "once daily", "route": "oral", "start": _d180, "status": "active",
             "notes": "Bone health supplementation"},
        ],
        "notes": [
            {"type": "soap", "content": "S: Morning stiffness 90 minutes. Bilateral MCP and PIP joint swelling and pain. Difficulty gripping objects.\nO: Warm, swollen MCPs bilaterally. DAS28 = 4.2. CRP 28 mg/L. X-ray: early erosions MCPs.\nA: Seropositive RA, moderate activity. Osteoporosis on DXA.\nP: MTX 15mg weekly + folic acid. Short-course prednisolone bridge. Rheumatology follow-up 6 weeks.", "ai": False},
        ],
    },
}


async def seed_clinical_db(user_ids: dict[str, str]) -> None:
    """Insert diagnoses, medications, and clinical notes for each patient.

    user_ids — mapping of {email: user_id} for all seeded users (doctors + patients).
    """
    engine = create_async_engine(_clinical_db_url(), echo=False)
    diag_count = med_count = note_count = 0

    # Build doctor-email → user_id lookup for FK columns
    doctor_for_patient: dict[str, str] = {p["email"]: p["doctor_email"] for p in PATIENTS}

    try:
        async with engine.begin() as conn:
            for patient_email, tpl in CLINICAL_TEMPLATES.items():
                patient_id = user_ids.get(patient_email)
                doc_email  = doctor_for_patient.get(patient_email)
                doctor_id  = user_ids.get(doc_email) if doc_email else None

                if not patient_id or not doctor_id:
                    continue

                # Idempotent: clear existing clinical data for this patient
                await conn.execute(
                    text("DELETE FROM diagnoses    WHERE patient_id = :pid"), {"pid": patient_id}
                )
                await conn.execute(
                    text("DELETE FROM medications  WHERE patient_id = :pid"), {"pid": patient_id}
                )
                await conn.execute(
                    text("DELETE FROM clinical_notes WHERE patient_id = :pid"), {"pid": patient_id}
                )

                # Diagnoses
                for d in tpl.get("diagnoses", []):
                    await conn.execute(
                        text("""
                            INSERT INTO diagnoses
                                (id, patient_id, doctor_id,
                                 icd10_code, diagnosis_name, diagnosis_detail,
                                 severity, status, diagnosed_at, source, created_at)
                            VALUES
                                (:id, :pid, :did,
                                 :icd, :name, :detail,
                                 :sev, :st, :dat, 'DOCTOR', NOW())
                        """),
                        {
                            "id":     str(uuid.uuid4()),
                            "pid":    patient_id,
                            "did":    doctor_id,
                            "icd":    d.get("icd10"),
                            "name":   d["name"],
                            "detail": d.get("detail"),
                            "sev":    d["severity"].upper() if d.get("severity") else None,
                            "st":     d["status"].upper(),
                            "dat":    d["date"],
                        },
                    )
                    diag_count += 1

                # Medications
                for m in tpl.get("medications", []):
                    await conn.execute(
                        text("""
                            INSERT INTO medications
                                (id, patient_id, doctor_id,
                                 drug_name, dosage, frequency, route,
                                 start_date, status, notes, created_at)
                            VALUES
                                (:id, :pid, :did,
                                 :drug, :dos, :freq, :route,
                                 :start, :st, :notes, NOW())
                        """),
                        {
                            "id":    str(uuid.uuid4()),
                            "pid":   patient_id,
                            "did":   doctor_id,
                            "drug":  m["drug"],
                            "dos":   m.get("dosage"),
                            "freq":  m.get("freq"),
                            "route": m.get("route"),
                            "start": m["start"],
                            "st":    m["status"].upper(),
                            "notes": m.get("notes"),
                        },
                    )
                    med_count += 1

                # Clinical notes
                for n in tpl.get("notes", []):
                    await conn.execute(
                        text("""
                            INSERT INTO clinical_notes
                                (id, patient_id, doctor_id,
                                 note_type, content, is_ai_generated, created_at)
                            VALUES
                                (:id, :pid, :did,
                                 :ntype, :content, :ai, NOW())
                        """),
                        {
                            "id":      str(uuid.uuid4()),
                            "pid":     patient_id,
                            "did":     doctor_id,
                            "ntype":   n["type"].upper() if n.get("type") else None,
                            "content": n["content"],
                            "ai":      n.get("ai", False),
                        },
                    )
                    note_count += 1

        print(
            f"  [clinical] Seeded {diag_count} diagnoses, "
            f"{med_count} medications, {note_count} clinical notes "
            f"across {len(CLINICAL_TEMPLATES)} patients."
        )
    finally:
        await engine.dispose()
