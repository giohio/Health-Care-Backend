"""Seed AI Service DB — triage sessions and chat sessions."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from .db_urls import _ai_db_url


# ──────────────────────────────────────────────────────────────────────────────
#  Realistic triage conversation scripts
# ──────────────────────────────────────────────────────────────────────────────

def _build_triage_messages(symptom: str, dept: str, urgency: str) -> list[dict]:
    """
    Build a realistic 4–6 turn triage conversation for the given symptom scenario.
    Returns a list of message dicts: [{"role": "user"|"assistant", "content": "..."}]
    """
    symptom_lower = symptom.lower()

    if "chest pain" in symptom_lower or "heart" in symptom_lower:
        return [
            {"role": "user",      "content": "Hello doctor, I've been experiencing chest pain, especially when climbing stairs."},
            {"role": "assistant", "content": "[Q] Chest pain during exertion could be related to cardiovascular issues. Do you have shortness of breath, palpitations, or pain radiating to your left shoulder? Do you have a history of cardiovascular disease or high blood pressure?"},
            {"role": "user",      "content": "Yes, I have shortness of breath and sometimes my heart races. I have a history of hypertension and type 2 diabetes."},
            {"role": "assistant", "content": "[Q] Thank you. How would you rate your chest pain — mild, moderate, or severe? And what medications are you currently taking for your pre-existing conditions?"},
            {"role": "user",      "content": "Moderate pain, I'm taking Metformin and Amlodipine."},
            {"role": "assistant", "content": "[Q] Do you smoke or drink alcohol? Does anyone in your family have cardiovascular disease?"},
            {"role": "user",      "content": "I smoke about 10 cigarettes a day, and my father had a myocardial infarction."},
            {"role": "assistant", "content": (
                "[R] Based on the information you've provided, I recommend scheduling an appointment at **Cardiology (Cardiology)**.\n\n"
                "**Priority Level: Priority** — Chest pain symptoms combined with history of hypertension, diabetes, smoking, and family history of cardiovascular disease require early evaluation by a cardiologist.\n\n"
                "**Note:** If you experience severe chest pain, severe shortness of breath, or fainting, go to the emergency department immediately."
            )},
        ]

    elif "headache" in symptom_lower or "migraine" in symptom_lower:
        return [
            {"role": "user",      "content": "Doctor, I've had a continuous headache for 3 days, pain on both temples."},
            {"role": "assistant", "content": "[Q] A continuous 3-day headache is a symptom that needs attention. Do you have fever, nausea, vomiting, sensitivity to light or noise? How would you rate the pain (1–10)?"},
            {"role": "user",      "content": "Slight nausea, no fever, pain about 6/10, and I'm very sensitive to light."},
            {"role": "assistant", "content": "[Q] Are you under stress or sleep-deprived? And have you had headaches like this before?"},
            {"role": "user",      "content": "I've been under stress this week, sleeping only 4–5 hours each night. I've had migraines before."},
            {"role": "assistant", "content": "[Q] Thank you. Are you taking any contraceptives, vasodilators, or other medications? Do you drink a lot of caffeine?"},
            {"role": "user",      "content": "I drink 3–4 cups of coffee daily, no contraceptives."},
            {"role": "assistant", "content": (
                "[R] With migraine symptoms accompanied by nausea, light sensitivity, stress, and sleep deprivation, I recommend seeing a **Neurology (Neurology)** specialist.\n\n"
                "**Priority Level: Priority** — Persistent headache in a patient with a history of migraine requires neurological evaluation to rule out more serious causes.\n\n"
                "**Note:** If you experience sudden severe headache, high fever, or confusion, go to the emergency department immediately."
            )},
        ]

    elif "cough" in symptom_lower or "shortness of breath" in symptom_lower or "breathing" in symptom_lower:
        return [
            {"role": "user",      "content": "Doctor, I've had a persistent cough for over 2 weeks, with phlegm and sometimes shortness of breath when exerting myself."},
            {"role": "assistant", "content": "[Q] A 2-week persistent cough with phlegm is a symptom that needs careful evaluation. Do you have fever, chills, chest pain when breathing deeply? What color is the phlegm?"},
            {"role": "user",      "content": "No fever, white phlegm, slight chest pain when coughing hard, and I have a history of asthma."},
            {"role": "assistant", "content": "[Q] With a history of asthma, this symptom may be related to respiratory disease. Do you smoke or have exposure to dust or smoke? What medications are you taking for asthma?"},
            {"role": "user",      "content": "I smoke about 5 cigarettes a day, and I use a Ventolin inhaler when needed."},
            {"role": "assistant", "content": (
                "[R] Based on your history of asthma, persistent cough, and shortness of breath combined with smoking, I recommend seeing a **General Medicine (General Medicine)** specialist.\n\n"
                "**Priority Level: Priority** — A General Medicine physician needs to evaluate your asthma control and rule out COPD or other lung diseases.\n\n"
                "**Note:** If you experience severe shortness of breath, rapid breathing, or bluish lips, go to the emergency department immediately."
            )},
        ]

    elif "rash" in symptom_lower or "itchy" in symptom_lower or "eczema" in symptom_lower or "psoriasis" in symptom_lower or "skin" in symptom_lower:
        return [
            {"role": "user",      "content": "Doctor, I've developed itchy red spots on my hands and legs that are spreading, lasting over 1 week."},
            {"role": "assistant", "content": "[Q] Spreading itchy red rash needs evaluation. Do you have fever, joint pain, or swollen lymph nodes? Have you been exposed to any unusual substances recently?"},
            {"role": "user",      "content": "No fever, no joint pain, but I used a new soap last week. Someone in my family has atopic dermatitis."},
            {"role": "assistant", "content": "[Q] Thank you. Are the red spots flaking, blistering, or just itchy? Have you tried any medications?"},
            {"role": "user",      "content": "Slight flaking, no medications yet, I only applied moisturizer."},
            {"role": "assistant", "content": (
                "[R] With itchy red rash with flaking in someone with a family history of atopic dermatitis, this could be contact dermatitis or recurrent atopic dermatitis. I recommend seeing a **Dermatology (Dermatology)** specialist.\n\n"
                "**Priority Level: Routine** — No acute serious signs, but a dermatologist needs to make an accurate diagnosis.\n\n"
                "**Note:** If the rash spreads rapidly, with fever or accompanied by breathing difficulty, go to the emergency department (could be severe allergic reaction)."
            )},
        ]

    elif "fever" in symptom_lower or "fatigue" in symptom_lower or "tired" in symptom_lower:
        return [
            {"role": "user",      "content": "Doctor, I have a mild fever of 37.8 degrees, fatigue, body aches, and a sore throat for 3 days."},
            {"role": "assistant", "content": "[Q] Fever with sore throat and fatigue could be an infection. Do you have cough, runny nose, headache, nausea, or diarrhea? Have you been exposed to sick people recently?"},
            {"role": "user",      "content": "Slight cough, no diarrhea, I work in an office where many people have colds."},
            {"role": "assistant", "content": "[Q] Thank you. Do you have abdominal pain, painful urination, or skin rash? Do you have a history of chronic disease?"},
            {"role": "user",      "content": "No abdominal pain, no painful urination, no rash. I'm healthy with no chronic diseases."},
            {"role": "assistant", "content": (
                "[R] Symptoms of mild fever, sore throat, body aches, and fatigue are consistent with an upper respiratory infection (possibly flu or viral pharyngitis). I recommend seeing a **General Medicine (General Medicine)** specialist.\n\n"
                "**Priority Level: Routine** — No acute dangerous signs, but a General Medicine physician should examine you and order tests if needed.\n\n"
                "**Note:** If fever exceeds 39 degrees, you have difficulty breathing, severe rash, or confusion, go to the emergency department immediately."
            )},
        ]

    elif "urinary" in symptom_lower or "kidney" in symptom_lower or "uti" in symptom_lower:
        return [
            {"role": "user",      "content": "Doctor, I have lower back pain, frequent urination, and painful urination for 2 days."},
            {"role": "assistant", "content": "[Q] Lower back pain with frequent painful urination suggests a urinary tract infection. Do you have fever, chills, flank pain, or bloody/pus in urine?"},
            {"role": "user",      "content": "Slight fever 37.5 degrees, no flank pain, slightly cloudy urine. I have a history of recurrent urinary tract infections."},
            {"role": "assistant", "content": "[Q] Thank you. Do you have kidney disease or kidney stones? Have you taken any antibiotics recently?"},
            {"role": "user",      "content": "No kidney stones, haven't taken antibiotics this time."},
            {"role": "assistant", "content": (
                "[R] With symptoms of painful urination, lower back pain, mild fever, and history of recurrent urinary tract infections, you may have a progressing urinary tract infection. I recommend seeing a **General Medicine (General Medicine)** specialist.\n\n"
                "**Priority Level: Priority** — A General Medicine physician needs to evaluate you, run urine tests, and culture to ensure timely treatment.\n\n"
                "**Note:** If fever exceeds 38.5 degrees, severe back pain, or significant blood in urine, go to the emergency department."
            )},
        ]

    elif "dizziness" in symptom_lower or "vertigo" in symptom_lower or "lightheaded" in symptom_lower:
        return [
            {"role": "user",      "content": "Doctor, I have sudden dizziness and vertigo, with nausea, occurring a few times per week."},
            {"role": "assistant", "content": "[Q] Vertigo with nausea needs differentiation between central and peripheral vestibular causes. Do you have tinnitus, hearing loss, severe headache, or numbness/weakness in limbs?"},
            {"role": "user",      "content": "No tinnitus, no hearing loss, but slight mild headache. I have a history of hypertension."},
            {"role": "assistant", "content": "[Q] Thank you. Are you stressed, sleep-deprived, or drinking a lot of alcohol? What medications are you taking for hypertension?"},
            {"role": "user",      "content": "Slightly stressed, sleeping 6 hours, drinking alcohol 2–3 times/week. I'm taking Amlodipine 5mg."},
            {"role": "assistant", "content": (
                "[R] Vertigo with headache in a patient with a history of hypertension needs careful evaluation. It may be related to vestibular disorders or cerebrovascular disease. I recommend seeing a **Neurology (Neurology)** specialist.\n\n"
                "**Priority Level: Priority** — A neurologist needs to evaluate the cause of dizziness and rule out cerebrovascular disease.\n\n"
                "**Note:** If you experience severe dizziness with slurred speech, one-sided numbness/weakness, or loss of consciousness, call emergency services immediately."
            )},
        ]

    elif "abdominal pain" in symptom_lower or "stomach pain" in symptom_lower or "belly" in symptom_lower:
        return [
            {"role": "user",      "content": "Doctor, I have epigastric pain, acid reflux, and bloating for 1 week."},
            {"role": "assistant", "content": "[Q] Epigastric pain with acid reflux suggests gastroesophageal disease. Do you have nausea, vomiting, black stool, or weight loss? Do you often eat irregularly or take NSAIDs?"},
            {"role": "user",      "content": "Slight nausea, no vomiting, normal stool. I often eat irregularly and take ibuprofen occasionally."},
            {"role": "assistant", "content": "[Q] Thank you. Are symptoms worse after eating, when hungry, or with no pattern? Do you drink alcohol?"},
            {"role": "user",      "content": "Pain is worse when hungry, I drink alcohol about once a week."},
            {"role": "assistant", "content": (
                "[R] Epigastric pain with acid reflux worse when hungry in someone using NSAIDs and alcohol suggests peptic ulcer disease. I recommend seeing a **General Medicine (General Medicine)** specialist for possible gastroscopy if needed.\n\n"
                "**Priority Level: Priority** — A General Medicine physician needs to evaluate, run tests, and provide appropriate treatment.\n\n"
                "**Note:** If you experience severe abdominal pain, vomiting blood, or black stool, go to the emergency department immediately."
            )},
        ]

    elif "leg swelling" in symptom_lower or "swollen leg" in symptom_lower or "varicose" in symptom_lower or "vein" in symptom_lower:
        return [
            {"role": "user",      "content": "Doctor, I have tired legs, swelling in both lower legs, visible veins on my calves, especially after standing for long periods."},
            {"role": "assistant", "content": "[Q] Bilateral lower limb swelling and visible veins suggest venous insufficiency. Do you have pain, burning sensation, skin discoloration, or ulcers on your legs? Do you have a history of heart, kidney, or liver disease?"},
            {"role": "user",      "content": "Slight mild pain, no ulcers, no heart kidney liver disease. I have a standing job."},
            {"role": "assistant", "content": "[Q] Thank you. Are you overweight, sedentary, or wear tight compression stockings? Do you take contraceptives or blood pressure medications?"},
            {"role": "user",      "content": "Slightly overweight, no contraceptives. I walk 30 minutes daily."},
            {"role": "assistant", "content": (
                "[R] Lower limb swelling, visible veins, and pain in someone who stands a lot suggests lower limb venous insufficiency. I recommend seeing a **General Medicine (General Medicine)** specialist for vascular ultrasound and treatment.\n\n"
                "**Priority Level: Routine** — No signs of acute deep vein thrombosis.\n\n"
                "**Note:** If you experience sudden one-sided leg swelling, severe pain, redness, or difficulty breathing, go to the emergency department (risk of thrombosis)."
            )},
        ]

    else:
        # Generic fallback
        return [
            {"role": "user",      "content": f"I have {symptom}."},
            {"role": "assistant", "content": "[Q] Thank you. Could you describe it in more detail? How long have these symptoms lasted, what is the severity, and are there any other accompanying symptoms?"},
            {"role": "user",      "content": "Symptoms have lasted about 1 week, moderate severity, no serious accompanying symptoms."},
            {"role": "assistant", "content": f"[R] With {symptom} symptoms lasting and moderate severity, I recommend seeing a **{dept}** specialist.\n\n**Priority Level: {urgency}** — You should be evaluated by a specialist soon."},
        ]


# ──────────────────────────────────────────────────────────────────────────────
#  Triage session seed scenarios
#  Maps patient_email → session definitions
# ──────────────────────────────────────────────────────────────────────────────

TRIAGE_SEEDS: dict[str, list[dict]] = {
    "patient.le.thi.mai@healthai.dev": [
        {
            "symptom":          "Chest pain when climbing stairs",
            "department":       "Cardiology",
            "urgency":          "Priority",
            "status":           "pending_review",
            "doctor_id":        "dr.nguyen.van.an@healthai.dev",
            "doctor_notes":     "Patient has history of hypertension and type 2 diabetes, smoking. Chest pain on exertion needs cardiac evaluation and ECG, cardiac enzyme tests.",
            "final_department": None,
            "days_ago":         5,
        },
    ],
    "patient.tran.van.long@healthai.dev": [
        {
            "symptom":          "Chest pain and shortness of breath on exertion",
            "department":       "Cardiology",
            "urgency":          "Emergency",
            "status":           "pending_review",
            "doctor_id":        "dr.nguyen.van.an@healthai.dev",
            "doctor_notes":     None,
            "final_department": None,
            "days_ago":         2,
        },
        {
            "symptom":          "Tired legs and swelling in both lower legs",
            "department":       "General Medicine",
            "urgency":          "Routine",
            "status":           "auto_confirmed",
            "doctor_id":        None,
            "doctor_notes":     None,
            "final_department": None,
            "days_ago":         12,
        },
    ],
    "patient.vo.thi.hoa@healthai.dev": [
        {
            "symptom":          "Prolonged migraine headache",
            "department":       "Neurology",
            "urgency":          "Priority",
            "status":           "doctor_confirmed",
            "doctor_id":        "dr.le.minh.duc@healthai.dev",
            "doctor_notes":     "Agreed with AI diagnosis. Patient has migraine history, needs prophylactic prescription and follow-up.",
            "final_department": "Neurology",
            "days_ago":         8,
        },
    ],
    "patient.nguyen.van.minh@healthai.dev": [
        {
            "symptom":          "Cough and shortness of breath on exertion",
            "department":       "General Medicine",
            "urgency":          "Priority",
            "status":           "pending_review",
            "doctor_id":        "dr.pham.thi.lan.huong@healthai.dev",
            "doctor_notes":     None,
            "final_department": None,
            "days_ago":         3,
        },
    ],
    "patient.hoang.thi.thu@healthai.dev": [
        {
            "symptom":          "Headache and vertigo",
            "department":       "Neurology",
            "urgency":          "Priority",
            "status":           "pending_review",
            "doctor_id":        "dr.le.minh.duc@healthai.dev",
            "doctor_notes":     None,
            "final_department": None,
            "days_ago":         1,
        },
    ],
    "patient.bui.van.duc@healthai.dev": [
        {
            "symptom":          "Severe headache and numbness in right arm",
            "department":       "Neurology",
            "urgency":          "Emergency",
            "status":           "pending_review",
            "doctor_id":        "dr.le.minh.duc@healthai.dev",
            "doctor_notes":     "Urgent brain MRI needed to rule out cerebrovascular accident.",
            "final_department": None,
            "days_ago":         1,
        },
    ],
    "patient.duong.van.khanh@healthai.dev": [
        {
            "symptom":          "Itchy red rash on hands and legs",
            "department":       "Dermatology",
            "urgency":          "Routine",
            "status":           "auto_confirmed",
            "doctor_id":        None,
            "doctor_notes":     None,
            "final_department": None,
            "days_ago":         10,
        },
    ],
    "patient.ngo.thi.xuan@healthai.dev": [
        {
            "symptom":          "Body-wide red peeling rash",
            "department":       "Dermatology",
            "urgency":          "Priority",
            "status":           "referred_internal",
            "doctor_id":        "dr.pham.hong.van@healthai.dev",
            "doctor_notes":     "Rash not typical of dermatology, needs General Medicine evaluation first to rule out systemic disease.",
            "final_department": "General Medicine",
            "days_ago":         4,
        },
    ],
    "patient.pham.thi.lan@healthai.dev": [
        {
            "symptom":          "Mild fever, fatigue, sore throat",
            "department":       "General Medicine",
            "urgency":          "Routine",
            "status":           "auto_confirmed",
            "doctor_id":        None,
            "doctor_notes":     None,
            "final_department": None,
            "days_ago":         6,
        },
    ],
    "patient.mai.thi.lien@healthai.dev": [
        {
            "symptom":          "Knee joint pain and morning stiffness",
            "department":       "General Medicine",
            "urgency":          "Routine",
            "status":           "auto_confirmed",
            "doctor_id":        None,
            "doctor_notes":     None,
            "final_department": None,
            "days_ago":         15,
        },
    ],
    "patient.cao.van.toan@healthai.dev": [
        {
            "symptom":          "Lower back pain and painful urination",
            "department":       "General Medicine",
            "urgency":          "Priority",
            "status":           "pending_review",
            "doctor_id":        "dr.hoang.van.minh@healthai.dev",
            "doctor_notes":     None,
            "final_department": None,
            "days_ago":         2,
        },
    ],
    "patient.dinh.thi.lan@healthai.dev": [
        {
            "symptom":          "Leg swelling, fatigue, and back pain",
            "department":       "General Medicine",
            "urgency":          "Priority",
            "status":           "doctor_confirmed",
            "doctor_id":        "dr.hoang.van.minh@healthai.dev",
            "doctor_notes":     "Agreed with General Medicine referral. Patient has CKD stage 3, needs renal function monitoring.",
            "final_department": "General Medicine",
            "days_ago":         7,
        },
    ],
    "patient.bui.thi.linh@healthai.dev": [
        {
            "symptom":          "Mild chest pain and shortness of breath when walking",
            "department":       "Cardiology",
            "urgency":          "Priority",
            "status":           "pending_review",
            "doctor_id":        "dr.nguyen.van.an@healthai.dev",
            "doctor_notes":     None,
            "final_department": None,
            "days_ago":         1,
        },
    ],
    "patient.truong.thi.mai@healthai.dev": [
        {
            "symptom":          "Palpitations, hand tremors, weight loss",
            "department":       "General Medicine",
            "urgency":          "Priority",
            "status":           "pending_review",
            "doctor_id":        "dr.tran.van.phuong@healthai.dev",
            "doctor_notes":     None,
            "final_department": None,
            "days_ago":         3,
        },
    ],
    "patient.vu.thi.hang@healthai.dev": [
        {
            "symptom":          "Fatigue, pale skin, dizziness",
            "department":       "General Medicine",
            "urgency":          "Priority",
            "status":           "pending_review",
            "doctor_id":        "dr.nguyen.thi.hue.linh@healthai.dev",
            "doctor_notes":     None,
            "final_department": None,
            "days_ago":         2,
        },
    ],
    "patient.le.thi.nam@healthai.dev": [
        {
            "symptom":          "Heart palpitations, irregular heartbeat",
            "department":       "Cardiology",
            "urgency":          "Priority",
            "status":           "pending_review",
            "doctor_id":        "dr.nguyen.van.an@healthai.dev",
            "doctor_notes":     None,
            "final_department": None,
            "days_ago":         1,
        },
    ],
    "patient.pham.van.khang@healthai.dev": [
        {
            "symptom":          "Persistent cough, shortness of breath, chest tightness",
            "department":       "General Medicine",
            "urgency":          "Emergency",
            "status":           "pending_review",
            "doctor_id":        "dr.pham.thi.lan.huong@healthai.dev",
            "doctor_notes":     None,
            "final_department": None,
            "days_ago":         0,
        },
    ],
    "patient.luu.thi.mai@healthai.dev": [
        {
            "symptom":          "Recurring asthma, nighttime shortness of breath",
            "department":       "General Medicine",
            "urgency":          "Priority",
            "status":           "doctor_confirmed",
            "doctor_id":        "dr.pham.thi.lan.huong@healthai.dev",
            "doctor_notes":     "Agreed. Need to check lung function and adjust inhaler medication regimen.",
            "final_department": "General Medicine",
            "days_ago":         6,
        },
    ],
}


# ──────────────────────────────────────────────────────────────────────────────
#  Chat session seed scenarios (lab_chat + clinical_assist)
# ──────────────────────────────────────────────────────────────────────────────

CHAT_SESSION_SEEDS: list[dict] = [
    {
        "user_email":     "dr.nguyen.van.an@healthai.dev",
        "user_role":      "doctor",
        "session_type":   "clinical_assist",
        "patient_email":  "patient.le.thi.mai@healthai.dev",
        "department":     "Cardiology",
        "days_ago":       10,
        "messages": [
            {"role": "user",      "content": "I need help creating a treatment plan for a 43-year-old female patient with hypertension and type 2 diabetes, presenting with chest pain on exertion."},
            {"role": "assistant", "content": "I'm ready to assist you. Please provide additional information: what medications is the patient currently taking, what are the latest test results (HbA1c, blood lipids, kidney function), and are there any abnormalities on the most recent ECG?"},
            {"role": "user",      "content": "HbA1c 7.8%, lipids normal, kidney function normal. ECG shows ST-T changes. Currently taking Metformin 1000mg twice daily and Amlodipine 5mg daily."},
            {"role": "assistant", "content": "Thank you. With HbA1c 7.8% and ECG showing ST-T changes in a patient with hypertension and type 2 diabetes, I recommend:\n\n1. **Glycemic control:** Consider adding SGLT2 inhibitor (Empagliflozin) — beneficial for heart and kidneys.\n2. **Blood pressure control:** Target <130/80 mmHg. Consider adding ARB (Losartan 50mg) if no contraindications.\n3. **Cardiovascular prevention:** Aspirin 81mg if no contraindications.\n4. **Additional tests:** Troponin, BNP, echocardiogram to assess cardiac function.\n5. **Follow-up in 2 weeks with test results."},
        ],
    },
    {
        "user_email":     "dr.le.minh.duc@healthai.dev",
        "user_role":      "doctor",
        "session_type":   "clinical_assist",
        "patient_email":  "patient.bui.van.duc@healthai.dev",
        "department":     "Neurology",
        "days_ago":       3,
        "messages": [
            {"role": "user",      "content": "I need help interpreting a brain MRI for a 60-year-old male patient with severe headache and right arm numbness."},
            {"role": "assistant", "content": "Let me help with the interpretation. Can you describe the lesions on the MRI? Specifically: location (cortical, white matter, brainstem, cerebellum), characteristics (T2/FLAIR hyperintensity, T1 hypointensity, restricted diffusion), size, and is there mass effect?"},
            {"role": "user",      "content": "T2/FLAIR hyperintense lesion in right hemisphere white matter, size 1.5x2cm, no mass effect, no restricted diffusion."},
            {"role": "assistant", "content": "With a T2/FLAIR hyperintense lesion in right hemisphere white matter, no restricted diffusion, no mass effect in a 60-year-old patient with cardiovascular risk factors, the possibilities include:\n\n1. **Cerebral small vessel disease** — possible white matter lesions due to chronic hypertension.\n2. **Primary/secondary brain tumor** — less likely without mass effect.\n3. **MS (Multiple Sclerosis)** — less likely at this age and without restricted diffusion.\n\n**Recommendation:** MRI with/without contrast needed to evaluate post-contrast enhancement. Complement, ANA, ANCA tests to rule out vasculitis. Close clinical follow-up."},
        ],
    },
    {
        "user_email":     "dr.pham.hong.van@healthai.dev",
        "user_role":      "doctor",
        "session_type":   "lab_chat",
        "patient_email":  "patient.ngo.thi.xuan@healthai.dev",
        "department":     "Dermatology",
        "days_ago":       5,
        "messages": [
            {"role": "user",      "content": "I need help reading blood test results for a 36-year-old female patient with generalized red rash."},
            {"role": "assistant", "content": "I'm ready to assist. Please provide the lab values: CBC (RBC, WBC, platelets, hemoglobin), liver function (ALT, AST, ALP, bilirubin), kidney function (creatinine, eGFR), CRP/ESR, and immunology tests if available (ANA, anti-dsDNA, complement)."},
            {"role": "user",      "content": "Hb 11.2 g/dL, WBC 11200, PLT 180000, CRP 35 mg/L (elevated), ALT 68, AST 45, ANA 1:320 positive, anti-dsDNA positive."},
            {"role": "assistant", "content": "With ANA 1:320 and anti-dsDNA positive, elevated CRP, mild anemia, and generalized red rash in a 36-year-old female — this clinical picture strongly suggests **Systemic Lupus Erythematosus (SLE)**.\n\n**Recommendations:**\n1. Additional tests: anti-Smith, anti-RNP, anti-SSA/SSB, complement C3/C4, anti-phospholipid antibodies, urine protein/creatinine ratio.\n2. Chest X-ray to rule out SLE-related interstitial pneumonia.\n3. Consultation with Rheumatology.\n4. **Transfer of care:** This exceeds simple dermatology scope. The patient needs comprehensive evaluation by a Rheumatologist and Nephrologist."},
        ],
    },
    {
        "user_email":     "dr.hoang.van.minh@healthai.dev",
        "user_role":      "doctor",
        "session_type":   "clinical_assist",
        "patient_email":  "patient.dinh.thi.lan@healthai.dev",
        "department":     "Nephrology",
        "days_ago":       8,
        "messages": [
            {"role": "user",      "content": "I need help managing a 60-year-old female patient, CKD stage 3, leg swelling and fatigue."},
            {"role": "assistant", "content": "I'm ready to assist. Please provide: latest eGFR, creatinine, serum albumin, hemoglobin, calcium, phosphate, PTH, and proteinuria status (protein amount/day or urine protein/creatinine ratio)."},
            {"role": "user",      "content": "eGFR 42 mL/min/1.73m², Creatinine 1.8 mg/dL, albumin 3.2 g/dL, Hb 9.5 g/dL, Ca 8.1 mg/dL (low), phosphate 4.8 mg/dL (elevated), PTH 85 pg/mL (elevated)."},
            {"role": "assistant", "content": "This is a CKD stage 3B patient with multiple complications:\n\n**Analysis:**\n1. **Anemia (Hb 9.5):** Due to reduced EPO — consider Erythropoiesis-Stimulating Agent (ESA).\n2. **Calcium-phosphate disorder (low Ca, high phosphate, high PTH):** Bone disease due to CKD.\n3. **Low albumin:** Malnutrition or protein loss through kidneys.\n\n**Treatment recommendations:**\n1. Restrict phosphate in diet, consider phosphate binder (Calcium carbonate).\n2. Supplement Calcitriol or vitamin D analog based on PTH.\n3. ESA for anemia if Hb < 10 g/dL.\n4. Blood pressure control < 130/80 (ACEi/ARB if no contraindications and proteinuria present).\n5. Monitor eGFR every 3 months.\n6. Consider Nephrology referral for renal replacement therapy preparation."},
        ],
    },
    {
        "user_email":     "patient.pham.thi.lan@healthai.dev",
        "user_role":      "patient",
        "session_type":   "lab_chat",
        "patient_email":  "patient.pham.thi.lan@healthai.dev",
        "department":     None,
        "days_ago":       4,
        "messages": [
            {"role": "user",      "content": "Doctor, I received my blood test results. Please explain: WBC 7200, RBC 4.2M, Hgb 11.8, PLT 245000, Glucose 95, CRP 3.2."},
            {"role": "assistant", "content": "Hello! Here is an explanation of your values:\n\n**Blood Count:**\n- WBC: 7,200 — **Normal** (4,500–11,000)\n- RBC: 4.2M — **Normal** for female\n- Hemoglobin: 11.8 g/dL — **Slightly low** (normal for female: 12–16 g/dL)\n- Platelets: 245,000 — **Normal** (150,000–400,000)\n\n**Biochemistry:**\n- Fasting Glucose: 95 mg/dL — **Normal** (< 100 mg/dL)\n- CRP: 3.2 mg/L — **Normal** (< 5 mg/L, no inflammation)\n\n**Summary:** Your values are generally good. Slightly low hemoglobin may be due to insufficient iron in your diet — you should eat more iron-rich foods (red meat, dark leafy greens, beans). If you experience prolonged fatigue, please schedule an appointment for further evaluation."},
        ],
    },
]


# ──────────────────────────────────────────────────────────────────────────────
#  Seed functions
# ──────────────────────────────────────────────────────────────────────────────

async def seed_triage_sessions(user_ids: dict[str, str]) -> list[dict]:
    """
    Insert triage sessions for various patients.
    Returns list of {patient_email, session_id} for summary.
    """
    engine = create_async_engine(_ai_db_url(), echo=False)
    seeded: list[dict] = []

    try:
        async with engine.begin() as conn:
            for patient_email, sessions in TRIAGE_SEEDS.items():
                patient_id = user_ids.get(patient_email)
                if not patient_id:
                    continue

                for sess in sessions:
                    session_id = str(uuid.uuid4())
                    messages   = _build_triage_messages(sess["symptom"], sess["department"], sess["urgency"])
                    created_at = datetime.now(tz=timezone.utc) - timedelta(days=sess["days_ago"])
                    updated_at = created_at + timedelta(hours=1)

                    # Map status string → DB enum (uppercase, underscore-separated)
                    status_map = {
                        "active":            "ACTIVE",
                        "auto_confirmed":    "AUTO_CONFIRMED",
                        "pending_review":    "PENDING_REVIEW",
                        "doctor_confirmed":  "DOCTOR_CONFIRMED",
                        "referred_internal": "REFERRED_INTERNAL",
                        "abandoned":         "ABANDONED",
                    }
                    status = status_map.get(sess["status"], "ACTIVE")

                    # Map urgency string → label used by service
                    urgency_map = {
                        "Routine":     "Routine",
                        "Priority":    "Priority",
                        "Emergency":   "Emergency",
                    }
                    urgency = urgency_map.get(sess["urgency"], "Priority")

                    # Get doctor_id if assigned
                    doctor_id = user_ids.get(sess["doctor_id"]) if sess["doctor_id"] else None

                    completed_at = None
                    if sess["status"] in ("auto_confirmed", "pending_review", "doctor_confirmed", "referred_internal"):
                        completed_at = updated_at

                    await conn.execute(
                        text("""
                            INSERT INTO triage_sessions
                                (id, patient_id, status, messages,
                                 suggested_department, urgency_level,
                                 doctor_id, final_department, doctor_notes,
                                 created_at, updated_at, completed_at)
                            VALUES
                                (:id, :pid, CAST(:status AS triagesessionstatus),
                                 CAST(:msgs AS jsonb),
                                 :sugg_dept, :urgency,
                                 :doc_id, :final_dept, :doc_notes,
                                 :created_at, :updated_at, :completed_at)
                            ON CONFLICT (id) DO UPDATE
                                SET messages             = EXCLUDED.messages,
                                    status               = EXCLUDED.status,
                                    suggested_department = EXCLUDED.suggested_department,
                                    urgency_level        = EXCLUDED.urgency_level,
                                    doctor_id            = EXCLUDED.doctor_id,
                                    final_department     = EXCLUDED.final_department,
                                    doctor_notes         = EXCLUDED.doctor_notes,
                                    completed_at         = EXCLUDED.completed_at,
                                    updated_at           = NOW()
                        """),
                        {
                            "id":          session_id,
                            "pid":         patient_id,
                            "status":      status,
                            "msgs":        __import__("json").dumps(messages),
                            "sugg_dept":   sess["department"],
                            "urgency":     urgency,
                            "doc_id":      doctor_id,
                            "final_dept":  sess.get("final_department"),
                            "doc_notes":   sess.get("doctor_notes"),
                            "created_at":  created_at,
                            "updated_at":  updated_at,
                            "completed_at": completed_at,
                        },
                    )

                    seeded.append({
                        "patient_email": patient_email,
                        "session_id":    session_id,
                        "symptom":       sess["symptom"],
                        "department":    sess["department"],
                        "urgency":       urgency,
                        "status":        status,
                    })

    finally:
        await engine.dispose()

    print(f"  [triage] Seeded {len(seeded)} triage sessions.")
    return seeded


async def seed_chat_sessions(user_ids: dict[str, str]) -> int:
    """
    Insert chat sessions (lab_chat + clinical_assist) for doctors and patients.
    Returns total count of chat sessions seeded.
    """
    engine = create_async_engine(_ai_db_url(), echo=False)
    total = 0

    try:
        async with engine.begin() as conn:
            for sess in CHAT_SESSION_SEEDS:
                user_id    = user_ids.get(sess["user_email"])
                patient_id = user_ids.get(sess["patient_email"]) if sess["patient_email"] else None
                if not user_id:
                    continue

                session_id = str(uuid.uuid4())
                created_at = datetime.now(tz=timezone.utc) - timedelta(days=sess["days_ago"])
                updated_at = created_at + timedelta(hours=len(sess["messages"]) * 0.5)

                await conn.execute(
                    text("""
                        INSERT INTO chat_sessions
                            (id, user_id, user_role, session_type, messages,
                             patient_id, department, created_at, updated_at)
                        VALUES
                            (:id, :uid, :role, :stype,
                             CAST(:msgs AS jsonb),
                             :pid, :dept, :created_at, :updated_at)
                        ON CONFLICT (id) DO UPDATE
                            SET messages    = EXCLUDED.messages,
                                updated_at  = NOW()
                    """),
                    {
                        "id":        session_id,
                        "uid":       user_id,
                        "role":      sess["user_role"],
                        "stype":     sess["session_type"],
                        "msgs":      __import__("json").dumps(sess["messages"]),
                        "pid":       patient_id,
                        "dept":      sess.get("department"),
                        "created_at": created_at,
                        "updated_at": updated_at,
                    },
                )
                total += 1

    finally:
        await engine.dispose()

    print(f"  [chat] Seeded {total} chat sessions.")
    return total
