"""Seed appointment DB — one set of appointments per doctor."""
import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from .db_urls import _appointment_db_url, _t
from .doctors import DOCTORS
from .patients import PATIENTS

# ── Appointment templates ────────────────────────────────────────────────────
# (appt_date, start, end, status, payment_status, chief_complaint, queue_number)

def _build_templates() -> dict[str, list[tuple]]:
    today      = date.today()
    d_minus30  = (today - timedelta(days=30)).isoformat()
    d_minus15  = (today - timedelta(days=15)).isoformat()
    d_today    = today.isoformat()

    return {
        "dr.nguyen.van.an@healthai.dev": [
            (d_minus30, "08:00:00", "08:30:00", "COMPLETED",   "PAID",   "Chest pain and shortness of breath",       1),
            (d_minus15, "09:00:00", "09:30:00", "COMPLETED",   "PAID",   "Follow-up blood pressure check",           2),
            (d_today,   "10:00:00", "10:30:00", "IN_PROGRESS", "PAID",   "Routine cardiac checkup",                  3),
            (d_today,   "11:00:00", "11:30:00", "CONFIRMED",   "PAID",   "Palpitations and dizziness",               4),
            (d_today,   "14:00:00", "14:30:00", "CONFIRMED",   "UNPAID", "Annual heart health screening",             5),
            (d_today,   "15:00:00", "15:30:00", "CONFIRMED",   "PAID",   "Heart valve follow-up",                    6),
            (d_today,   "15:30:00", "16:00:00", "CONFIRMED",   "PAID",   "Hypertension consultation",                7),
            (d_today,   "16:00:00", "16:30:00", "CONFIRMED",   "UNPAID", "Arrhythmia monitoring review",             8),
        ],
        "dr.tran.thi.bich@healthai.dev": [
            (d_minus30, "07:30:00", "08:00:00", "COMPLETED",   "PAID",   "Fever and persistent cough",               1),
            (d_minus15, "08:00:00", "08:30:00", "COMPLETED",   "PAID",   "Annual health check-up",                   2),
            (d_today,   "09:00:00", "09:30:00", "IN_PROGRESS", "PAID",   "General medicine consultation",            3),
            (d_today,   "10:00:00", "10:30:00", "CONFIRMED",   "PAID",   "Chronic fatigue follow-up",               4),
            (d_today,   "14:30:00", "15:00:00", "CONFIRMED",   "UNPAID", "Preventive health screening",              5),
            (d_today,   "15:00:00", "15:30:00", "CONFIRMED",   "PAID",   "Digestive issues review",                 6),
            (d_today,   "15:30:00", "16:00:00", "CONFIRMED",   "PAID",   "Seasonal allergy check",                  7),
            (d_today,   "16:00:00", "16:30:00", "CONFIRMED",   "UNPAID", "General wellness exam",                   8),
        ],
        "dr.le.minh.duc@healthai.dev": [
            (d_minus30, "08:00:00", "08:45:00", "COMPLETED",   "PAID",   "Severe recurring headaches",               1),
            (d_minus15, "09:00:00", "09:45:00", "COMPLETED",   "PAID",   "Memory loss and dizziness",                2),
            (d_today,   "10:00:00", "10:45:00", "IN_PROGRESS", "PAID",   "Epilepsy medication review",               3),
            (d_today,   "11:00:00", "11:45:00", "CONFIRMED",   "PAID",   "Stroke screening assessment",             4),
            (d_today,   "14:00:00", "14:45:00", "CONFIRMED",   "UNPAID", "Sleep disorder consultation",              5),
            (d_today,   "14:45:00", "15:30:00", "CONFIRMED",   "PAID",   "Migraine treatment adjustment",           6),
            (d_today,   "15:30:00", "16:15:00", "CONFIRMED",   "PAID",   "Neuropathy scan results",                 7),
            (d_today,   "16:15:00", "17:00:00", "CONFIRMED",   "UNPAID", "Multiple Sclerosis follow-up",            8),
        ],
        "dr.pham.hong.van@healthai.dev": [
            (d_minus30, "08:00:00", "08:30:00", "COMPLETED",   "PAID",   "Skin rash and itching",                   1),
            (d_minus15, "09:00:00", "09:30:00", "COMPLETED",   "PAID",   "Acne flare-up consultation",              2),
            (d_today,   "10:00:00", "10:30:00", "IN_PROGRESS", "PAID",   "Eczema follow-up",                        3),
            (d_today,   "11:00:00", "11:30:00", "CONFIRMED",   "PAID",   "Mole examination and biopsy",            4),
            (d_today,   "14:00:00", "14:30:00", "CONFIRMED",   "UNPAID", "Psoriasis management review",             5),
            (d_today,   "14:30:00", "15:00:00", "CONFIRMED",   "PAID",   "Fungal infection treatment",              6),
            (d_today,   "15:00:00", "15:30:00", "CONFIRMED",   "PAID",   "Cosmetic dermatology consult",            7),
            (d_today,   "15:30:00", "16:00:00", "CONFIRMED",   "UNPAID", "Dermatitis follow-up",                    8),
        ],
        "dr.vo.thanh.tung@healthai.dev": [
            (d_minus30, "08:00:00", "08:30:00", "COMPLETED",   "PAID",   "Knee pain after sports injury",           1),
            (d_minus15, "09:00:00", "09:30:00", "COMPLETED",   "PAID",   "Joint pain and stiffness",                2),
            (d_today,   "10:00:00", "10:30:00", "IN_PROGRESS", "PAID",   "Post-surgery rehabilitation check",       3),
            (d_today,   "11:00:00", "11:30:00", "CONFIRMED",   "PAID",   "Back pain consultation",                 4),
            (d_today,   "14:00:00", "14:30:00", "CONFIRMED",   "UNPAID", "Osteoporosis screening",                  5),
            (d_today,   "14:30:00", "15:00:00", "CONFIRMED",   "PAID",   "Shoulder injury assessment",             6),
            (d_today,   "15:00:00", "15:30:00", "CONFIRMED",   "PAID",   "Arthritis medication review",             7),
            (d_today,   "15:30:00", "16:00:00", "CONFIRMED",   "UNPAID", "Hip pain follow-up",                      8),
        ],
        "dr.pham.thi.lan.huong@healthai.dev": [
            (d_minus30, "08:00:00", "08:30:00", "COMPLETED",   "PAID",   "Persistent cough and sputum production",  1),
            (d_minus15, "09:00:00", "09:30:00", "COMPLETED",   "PAID",   "Follow-up for COPD management",          2),
            (d_today,   "10:00:00", "10:30:00", "IN_PROGRESS", "PAID",   "Annual respiratory checkup",              3),
            (d_today,   "11:00:00", "11:30:00", "CONFIRMED",   "PAID",   "Tuberculosis screening",                 4),
            (d_today,   "14:00:00", "14:30:00", "CONFIRMED",   "UNPAID", "Pulmonary function test review",          5),
            (d_today,   "14:30:00", "15:00:00", "CONFIRMED",   "PAID",   "Asthma flare-up management",              6),
            (d_today,   "15:00:00", "15:30:00", "CONFIRMED",   "PAID",   "Pneumonia recovery check",               7),
            (d_today,   "16:00:00", "16:30:00", "CONFIRMED",   "UNPAID", "Sleep apnea consultation",               8),
        ],
        "dr.hoang.van.minh@healthai.dev": [
            (d_minus30, "08:00:00", "08:30:00", "COMPLETED",   "PAID",   "Kidney function follow-up for CKD",       1),
            (d_minus15, "09:00:00", "09:30:00", "COMPLETED",   "PAID",   "Blood pressure and edema evaluation",    2),
            (d_today,   "10:00:00", "10:30:00", "IN_PROGRESS", "PAID",   "Routine nephrology consultation",         3),
            (d_today,   "11:00:00", "11:30:00", "CONFIRMED",   "PAID",   "Dialysis access evaluation",           4),
            (d_today,   "14:00:00", "14:30:00", "CONFIRMED",   "UNPAID", "Urinary tract infection review",          5),
            (d_today,   "14:30:00", "15:00:00", "CONFIRMED",   "PAID",   "Electrolyte imbalance follow-up",         6),
            (d_today,   "15:00:00", "15:30:00", "CONFIRMED",   "PAID",   "Glomerulonephritis monitoring",           7),
            (d_today,   "15:30:00", "16:00:00", "CONFIRMED",   "UNPAID", "Renal stone management review",           8),
        ],
        "dr.nguyen.thi.hue.linh@healthai.dev": [
            (d_minus30, "08:00:00", "08:30:00", "COMPLETED",   "PAID",   "Fatigue and pallor evaluation",           1),
            (d_minus15, "09:00:00", "09:30:00", "COMPLETED",   "PAID",   "CBC follow-up for anemia",               2),
            (d_today,   "10:00:00", "10:30:00", "IN_PROGRESS", "PAID",   "Hematology consultation",                3),
            (d_today,   "11:00:00", "11:30:00", "CONFIRMED",   "PAID",   "Leukemia screening consultation",        4),
            (d_today,   "14:00:00", "14:30:00", "CONFIRMED",   "UNPAID", "Blood clot evaluation",                   5),
            (d_today,   "14:30:00", "15:00:00", "CONFIRMED",   "PAID",   "Iron deficiency checkup",                6),
            (d_today,   "15:00:00", "15:30:00", "CONFIRMED",   "PAID",   "Bleeding disorder assessment",            7),
            (d_today,   "15:30:00", "16:00:00", "CONFIRMED",   "UNPAID", "Lymphoma follow-up",                      8),
        ],
        "dr.tran.van.phuong@healthai.dev": [
            (d_minus30, "08:00:00", "08:30:00", "COMPLETED",   "PAID",   "Diabetes medication adjustment",          1),
            (d_minus15, "09:00:00", "09:30:00", "COMPLETED",   "PAID",   "Thyroid nodule evaluation",              2),
            (d_today,   "10:00:00", "10:30:00", "IN_PROGRESS", "PAID",   "Endocrinology routine checkup",          3),
            (d_today,   "11:00:00", "11:30:00", "CONFIRMED",   "PAID",   "Obesity management consultation",        4),
            (d_today,   "14:00:00", "14:30:00", "CONFIRMED",   "UNPAID", "Adrenal disorder evaluation",             5),
            (d_today,   "14:30:00", "15:00:00", "CONFIRMED",   "PAID",   "Gestational diabetes check",              6),
            (d_today,   "15:00:00", "15:30:00", "CONFIRMED",   "PAID",   "Hormone replacement therapy review",      7),
            (d_today,   "15:30:00", "16:00:00", "CONFIRMED",   "UNPAID", "Pituitary gland monitoring",              8),
        ],
    }


CONSULTATION_FEES: dict[str, int] = {
    "dr.nguyen.van.an@healthai.dev":        350000,
    "dr.tran.thi.bich@healthai.dev":        180000,
    "dr.le.minh.duc@healthai.dev":          400000,
    "dr.pham.hong.van@healthai.dev":        250000,
    "dr.vo.thanh.tung@healthai.dev":        180000,
    "dr.pham.thi.lan.huong@healthai.dev":  300000,
    "dr.hoang.van.minh@healthai.dev":       350000,
    "dr.nguyen.thi.hue.linh@healthai.dev":  320000,
    "dr.tran.van.phuong@healthai.dev":      330000,
}


async def seed_appointment_db(
    patient_data: dict[str, dict],
    user_ids: dict[str, str],
    doctor_specialty_ids: dict[str, str],
) -> list[dict]:
    """Insert appointments per doctor (COMPLETED, IN_PROGRESS, CONFIRMED slots).

    Returns the completed appointment rows needed for EMR seeding.
    """
    patients_by_doctor: dict[str, list[str]] = {}
    for p in PATIENTS:
        patients_by_doctor.setdefault(p["doctor_email"], []).append(p["email"])

    APPT_TEMPLATES = _build_templates()
    completed_appointments: list[dict] = []
    in_progress_appointments: list[dict] = []
    engine = create_async_engine(_appointment_db_url(), echo=False)
    try:
        async with engine.begin() as conn:
            for doc in DOCTORS:
                doc_email  = doc["email"]
                doctor_id  = user_ids[doc_email]
                # Idempotent re-run: clear existing appointments for this doctor
                await conn.execute(
                    text("DELETE FROM appointments WHERE doctor_id = :did"), {"did": doctor_id}
                )
                specialty_id  = doctor_specialty_ids[doc_email]
                fee           = CONSULTATION_FEES[doc_email]
                doc_patients  = patients_by_doctor[doc_email]
                templates     = APPT_TEMPLATES[doc_email]

                for i, (appt_date, start, end, status, pay_status, complaint, q_num) in enumerate(templates):
                    patient_user_id = patient_data[doc_patients[i % len(doc_patients)]]["user_id"]
                    appt_id         = str(uuid.uuid4())
                    appt_date_obj   = date.fromisoformat(appt_date)
                    hh_e, mm_e, ss_e = (int(x) for x in end.split(":"))
                    conf_at = (
                        datetime(appt_date_obj.year, appt_date_obj.month, appt_date_obj.day, 7, 0)
                        if status == "CONFIRMED" else None
                    )
                    comp_at = (
                        datetime(appt_date_obj.year, appt_date_obj.month, appt_date_obj.day, hh_e, mm_e, ss_e)
                        if status == "COMPLETED" else None
                    )
                    await conn.execute(
                        text("""
                            INSERT INTO appointments
                                (id, patient_id, doctor_id, specialty_id,
                                 appointment_date, start_time, end_time,
                                 appointment_type, chief_complaint,
                                 status, payment_status, consultation_fee,
                                 queue_number, confirmed_at, completed_at,
                                 reminder_24h_sent, reminder_1h_sent)
                            VALUES
                                (:id, :pid, :did, :spid,
                                 :apdt, :st, :et,
                                 'general', :complaint,
                                 :status, :pay, :fee,
                                 :q, :conf_at, :comp_at,
                                 FALSE, FALSE)
                            ON CONFLICT (id) DO NOTHING
                        """),
                        {
                            "id": appt_id, "pid": patient_user_id,
                            "did": doctor_id, "spid": specialty_id,
                            "apdt": appt_date_obj,
                            "st": _t(start), "et": _t(end),
                            "complaint": complaint,
                            "status": status, "pay": pay_status,
                            "fee": fee, "q": q_num,
                            "conf_at": conf_at, "comp_at": comp_at,
                        },
                    )
                    if status == "COMPLETED":
                        completed_appointments.append({
                            "id":              appt_id,
                            "doctor_id":       doctor_id,
                            "patient_user_id": patient_user_id,
                            "doctor_email":    doc_email,
                            "date":            appt_date,
                        })
                    elif status == "IN_PROGRESS":
                        in_progress_appointments.append({
                            "id":              appt_id,
                            "doctor_id":       doctor_id,
                            "patient_user_id": patient_user_id,
                            "doctor_email":    doc_email,
                            "date":            appt_date,
                            "complaint":       complaint,
                        })

        n_total = sum(len(t) for t in APPT_TEMPLATES.values())
        print(f"  [appointment] Seeded {n_total} appointments ({len(completed_appointments)} completed, {len(in_progress_appointments)} in-progress).")
    finally:
        await engine.dispose()

    return completed_appointments, in_progress_appointments
