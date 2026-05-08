"""Seed patient DB — patient profiles and health backgrounds."""
import json
import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from .db_urls import _patient_db_url
from .patients import PATIENTS


async def seed_patient_db(user_ids: dict[str, str]) -> dict[str, dict]:
    """Insert patient profiles and health backgrounds (auth already done by seed_auth_db).

    user_ids — mapping of {email: user_id} from seed_auth_db.
    Returns {patient_email: {"user_id": str, "profile_id": str}}.
    """
    patient_data: dict[str, dict] = {
        p["email"]: {"user_id": user_ids[p["email"]]}
        for p in PATIENTS
        if p["email"] in user_ids
    }

    # Patient profiles + health backgrounds
    patient_engine = create_async_engine(_patient_db_url(), echo=False)
    try:
        async with patient_engine.begin() as conn:
            for p in PATIENTS:
                user_id = patient_data[p["email"]]["user_id"]
                profile_id = str(uuid.uuid4())
                await conn.execute(
                    text("""
                        INSERT INTO patient_profiles
                            (id, user_id, full_name, date_of_birth, gender,
                             phone_number, address, created_at, updated_at)
                        VALUES (:id, :uid, :name, :dob, CAST(:gender AS gender),
                                :phone, :address, NOW(), NOW())
                        ON CONFLICT (user_id) DO UPDATE
                            SET full_name     = EXCLUDED.full_name,
                                date_of_birth = EXCLUDED.date_of_birth,
                                gender        = EXCLUDED.gender,
                                phone_number  = EXCLUDED.phone_number,
                                address       = EXCLUDED.address,
                                updated_at    = NOW()
                    """),
                    {
                        "id": profile_id, "uid": user_id,
                        "name": p["full_name"],
                        "dob": date.fromisoformat(p["dob"]),
                        "gender": p["gender"],
                        "phone": p["phone"],
                        "address": p["address"],
                    },
                )
                row = await conn.execute(
                    text("SELECT id FROM patient_profiles WHERE user_id = :uid"),
                    {"uid": user_id},
                )
                patient_data[p["email"]]["profile_id"] = str(row.scalar_one())

                # Health background (PK = patient_id)
                await conn.execute(
                    text("""
                        INSERT INTO patient_health_backgrounds
                            (patient_id, blood_type, height_cm, weight_kg,
                             allergies, chronic_conditions)
                        VALUES (:pid, CAST(:bt AS bloodtype),
                                :h, :w,
                                CAST(:al AS jsonb), CAST(:cc AS jsonb))
                        ON CONFLICT (patient_id) DO UPDATE
                            SET blood_type         = EXCLUDED.blood_type,
                                height_cm          = EXCLUDED.height_cm,
                                weight_kg          = EXCLUDED.weight_kg,
                                allergies          = EXCLUDED.allergies,
                                chronic_conditions = EXCLUDED.chronic_conditions
                    """),
                    {
                        "pid": patient_data[p["email"]]["profile_id"],
                        "bt":  p["blood_type"],
                        "h":   p["height_cm"],
                        "w":   p["weight_kg"],
                        "al":  json.dumps(p["allergies"]),
                        "cc":  json.dumps(p["conditions"]),
                    },
                )
        print(f"  [patient] Seeded {len(PATIENTS)} patient profiles + health backgrounds.")
    finally:
        await patient_engine.dispose()

    return patient_data


async def seed_patient_vitals(user_ids: dict[str, str], patient_data: dict[str, dict]) -> None:
    """Insert 4 historical vitals readings per patient into patient_vitals."""
    engine = create_async_engine(_patient_db_url(), echo=False)
    total = 0
    # Realistic per-patient vitals snapshots: vary slightly across 4 time points
    # Format: list of (delta_days, height_cm, weight_kg, sbp, dbp, hr, temp)
    # Keyed by patient email — patients not listed get generic values derived from their profile
    VITALS_HISTORY: dict[str, list[tuple]] = {
        # Cardiology
        "patient.le.thi.mai@healthai.dev":     [(-180,165,62,128,82,74,36.6),(-90,165,61,132,84,76,36.5),(-30,165,61,130,82,72,36.7),(0,165,60,126,80,70,36.5)],
        "patient.tran.van.long@healthai.dev":  [(-180,170,88,148,94,82,36.8),(-90,170,90,150,96,84,36.9),(-30,170,89,144,92,80,36.7),(0,170,88,140,90,78,36.6)],
        "patient.vo.thi.hoa@healthai.dev":     [(-180,158,55,118,76,68,36.4),(-90,158,56,122,78,70,36.6),(-30,158,55,120,76,69,36.5),(0,158,55,118,75,68,36.5)],
        "patient.nguyen.thi.bich@healthai.dev":[(-180,162,72,138,88,80,36.7),(-90,162,71,136,86,78,36.6),(-30,162,70,134,85,76,36.5),(0,162,70,132,84,76,36.5)],
        "patient.pham.van.an@healthai.dev":    [(-180,175,95,145,92,86,36.9),(-90,175,96,148,94,88,37.0),(-30,175,94,144,90,84,36.8),(0,175,93,142,90,83,36.7)],
        # General Medicine
        "patient.nguyen.van.minh@healthai.dev":[(-180,168,70,122,80,72,36.6),(-90,168,71,124,82,74,36.5),(-30,168,70,120,78,70,36.6),(0,168,70,118,78,70,36.5)],
        "patient.pham.thi.lan@healthai.dev":   [(-180,155,52,116,74,68,36.4),(-90,155,53,118,76,70,36.6),(-30,155,52,116,74,68,36.5),(0,155,52,114,74,67,36.4)],
        "patient.le.van.thanh@healthai.dev":   [(-180,172,80,136,86,78,36.7),(-90,172,81,138,88,80,36.8),(-30,172,80,134,85,76,36.6),(0,172,79,132,84,75,36.6)],
        "patient.tran.thi.hoa@healthai.dev":   [(-180,160,65,128,82,74,36.5),(-90,160,64,126,80,72,36.4),(-30,160,64,124,80,70,36.5),(0,160,63,122,78,70,36.4)],
        "patient.vo.van.long@healthai.dev":    [(-180,178,84,130,84,76,36.6),(-90,178,85,132,86,78,36.7),(-30,178,84,128,82,75,36.6),(0,178,83,128,80,74,36.5)],
        # Neurology
        "patient.hoang.thi.thu@healthai.dev":  [(-180,163,60,118,76,70,36.5),(-90,163,60,120,78,72,36.6),(-30,163,59,116,74,68,36.5),(0,163,59,114,74,68,36.4)],
        "patient.bui.van.duc@healthai.dev":    [(-180,174,78,124,80,74,36.6),(-90,174,79,126,82,76,36.7),(-30,174,78,122,80,73,36.5),(0,174,78,120,78,72,36.5)],
        "patient.ly.thi.tuyet@healthai.dev":   [(-180,157,54,122,80,72,36.5),(-90,157,54,124,82,74,36.6),(-30,157,53,120,78,70,36.4),(0,157,53,118,78,70,36.4)],
        "patient.dinh.van.phu@healthai.dev":   [(-180,180,90,138,88,82,36.8),(-90,180,91,140,90,84,36.9),(-30,180,89,136,86,80,36.7),(0,180,89,134,85,79,36.7)],
        "patient.truong.thi.lan@healthai.dev": [(-180,161,58,120,78,72,36.5),(-90,161,58,122,80,74,36.6),(-30,161,57,118,76,70,36.5),(0,161,57,116,76,69,36.4)],
        # Dermatology
        "patient.duong.van.khanh@healthai.dev":[(-180,169,74,126,82,74,36.6),(-90,169,74,128,84,76,36.7),(-30,169,73,124,80,73,36.5),(0,169,73,122,80,72,36.5)],
        "patient.ngo.thi.xuan@healthai.dev":   [(-180,156,62,118,76,70,36.4),(-90,156,62,120,78,72,36.5),(-30,156,61,116,74,68,36.4),(0,156,61,115,74,68,36.4)],
        "patient.le.van.binh@healthai.dev":    [(-180,173,82,134,86,78,36.7),(-90,173,83,136,88,80,36.8),(-30,173,82,132,84,76,36.6),(0,173,81,130,84,75,36.6)],
        "patient.nguyen.thi.mai@healthai.dev": [(-180,158,57,120,78,70,36.5),(-90,158,57,122,80,72,36.5),(-30,158,56,118,76,70,36.4),(0,158,56,116,76,68,36.4)],
        "patient.vo.van.tung@healthai.dev":    [(-180,176,86,132,84,76,36.7),(-90,176,87,134,86,78,36.8),(-30,176,85,130,82,75,36.6),(0,176,85,128,82,74,36.6)],
        "patient.trinh.van.hung@healthai.dev": [(-180,178,71,118,76,70,36.5),(-90,178,70,120,78,72,36.6),(-30,178,70,116,74,69,36.5),(0,178,70,115,74,68,36.4)],
        # General / Ortho
        "patient.mai.thi.lien@healthai.dev":   [(-180,155,70,134,86,78,36.6),(-90,155,71,136,88,80,36.7),(-30,155,70,132,84,76,36.5),(0,155,70,130,84,76,36.5)],
        "patient.cao.van.toan@healthai.dev":   [(-180,168,75,128,82,74,36.6),(-90,168,75,130,84,76,36.7),(-30,168,74,126,80,72,36.5),(0,168,74,124,80,72,36.5)],
        "patient.dang.thi.huong@healthai.dev": [(-180,159,61,122,78,70,36.5),(-90,159,61,124,80,72,36.6),(-30,159,60,120,76,70,36.4),(0,159,60,118,76,69,36.4)],
        "patient.bui.van.long@healthai.dev":   [(-180,177,88,140,90,82,36.8),(-90,177,89,142,92,84,36.9),(-30,177,87,138,88,80,36.7),(0,177,87,136,88,80,36.7)],
        "patient.le.thi.thu@healthai.dev":     [(-180,162,64,120,78,70,36.5),(-90,162,64,122,80,72,36.6),(-30,162,63,118,76,70,36.5),(0,162,63,118,76,69,36.4)],
        # Respiratory
        "patient.pham.van.khang@healthai.dev": [(-180,171,79,136,88,80,36.7),(-90,171,80,140,90,84,36.9),(-30,171,78,134,86,78,36.7),(0,171,78,132,86,78,36.6)],
        "patient.luu.thi.mai@healthai.dev":    [(-180,157,56,118,76,70,36.5),(-90,157,57,120,78,72,36.6),(-30,157,56,116,74,68,36.4),(0,157,56,114,74,68,36.4)],
        "patient.nguyen.van.son@healthai.dev": [(-180,170,82,138,88,80,36.8),(-90,170,83,140,90,82,36.9),(-30,170,81,136,86,79,36.7),(0,170,81,134,86,79,36.7)],
        "patient.tran.thi.lan@healthai.dev":   [(-180,160,60,120,78,70,36.5),(-90,160,60,122,80,72,36.6),(-30,160,59,118,76,70,36.5),(0,160,59,116,76,69,36.4)],
        "patient.ho.van.minh@healthai.dev":    [(-180,174,78,132,84,76,36.6),(-90,174,79,134,86,78,36.7),(-30,174,78,130,82,74,36.6),(0,174,78,128,82,74,36.5)],
        # Nephrology
        "patient.dinh.thi.lan@healthai.dev":   [(-180,158,62,148,96,82,36.7),(-90,158,62,152,98,84,36.8),(-30,158,61,146,94,80,36.7),(0,158,61,144,92,80,36.6)],
        "patient.nguyen.thi.thanh@healthai.dev":[(-180,162,64,130,84,74,36.5),(-90,162,65,134,86,76,36.7),(-30,162,64,128,82,73,36.5),(0,162,63,126,82,72,36.5)],
        "patient.le.van.hung@healthai.dev":    [(-180,175,85,142,92,82,36.8),(-90,175,86,146,94,84,36.9),(-30,175,84,140,90,80,36.7),(0,175,84,138,90,80,36.7)],
        "patient.pham.thi.hoa@healthai.dev":   [(-180,155,58,128,84,76,36.6),(-90,155,58,130,86,78,36.7),(-30,155,57,126,82,74,36.5),(0,155,57,124,82,74,36.5)],
        "patient.tran.van.duc@healthai.dev":   [(-180,170,79,136,88,80,36.7),(-90,170,80,140,90,82,36.8),(-30,170,78,134,86,79,36.6),(0,170,78,132,86,78,36.6)],
        # Hematology
        "patient.vu.thi.hang@healthai.dev":    [(-180,160,52,110,72,80,36.4),(-90,160,52,112,74,82,36.5),(-30,160,51,110,72,78,36.4),(0,160,51,108,70,76,36.4)],
        "patient.nguyen.van.duc@healthai.dev": [(-180,174,76,124,80,74,36.6),(-90,174,77,126,82,76,36.7),(-30,174,76,122,78,72,36.5),(0,174,75,120,78,72,36.5)],
        "patient.tran.thi.thu@healthai.dev":   [(-180,159,55,116,74,72,36.4),(-90,159,55,118,76,74,36.5),(-30,159,54,114,72,70,36.4),(0,159,54,112,72,70,36.3)],
        "patient.le.van.nam@healthai.dev":     [(-180,171,80,130,82,76,36.6),(-90,171,81,132,84,78,36.7),(-30,171,79,128,80,75,36.6),(0,171,79,126,80,74,36.5)],
        "patient.hoang.thi.lan@healthai.dev":  [(-180,158,60,120,78,72,36.5),(-90,158,60,122,80,74,36.6),(-30,158,59,118,76,70,36.4),(0,158,59,116,76,70,36.4)],
        # Endocrinology
        "patient.bui.thi.linh@healthai.dev":   [(-180,160,84,152,98,86,36.9),(-90,160,85,156,100,88,37.0),(-30,160,83,148,96,84,36.8),(0,160,83,146,94,84,36.8)],
        "patient.do.van.hung@healthai.dev":    [(-180,173,82,136,86,78,36.7),(-90,173,83,138,88,80,36.8),(-30,173,81,134,84,76,36.6),(0,173,81,132,84,76,36.6)],
        "patient.truong.thi.mai@healthai.dev": [(-180,156,60,118,76,84,36.4),(-90,156,59,114,74,88,36.3),(-30,156,59,112,72,90,36.3),(0,156,58,110,70,92,36.3)],
        "patient.nguyen.van.an@healthai.dev":  [(-180,168,74,130,84,76,36.6),(-90,168,75,132,86,78,36.7),(-30,168,74,128,82,74,36.6),(0,168,73,126,82,74,36.5)],
        "patient.pham.thi.bich@healthai.dev":  [(-180,162,67,126,82,72,36.5),(-90,162,68,128,84,74,36.6),(-30,162,67,124,80,72,36.5),(0,162,66,122,80,70,36.4)],
    }
    today = datetime.now()
    vitals_engine = create_async_engine(_patient_db_url(), echo=False)
    try:
        async with vitals_engine.begin() as conn:
            for patient_info in PATIENTS:
                p_email    = patient_info["email"]
                patient_id = patient_data.get(p_email, {}).get("profile_id")
                doc_email  = patient_info.get("doctor_email", "")
                doctor_id  = user_ids.get(doc_email)
                if not patient_id or not doctor_id:
                    continue
                # Clear existing vitals for idempotent re-run
                await conn.execute(
                    text("DELETE FROM patient_vitals WHERE patient_id = :pid"), {"pid": patient_id}
                )
                readings = VITALS_HISTORY.get(p_email)
                if not readings:
                    # Generic fallback: 4 readings using profile height/weight
                    h = patient_info.get("height_cm", 165)
                    w = patient_info.get("weight_kg", 65)
                    readings = [
                        (-180, h, w,     128, 82, 74, 36.6),
                        (-90,  h, w - 1, 126, 80, 72, 36.5),
                        (-30,  h, w - 1, 124, 80, 70, 36.5),
                        (0,    h, w - 1, 122, 78, 70, 36.4),
                    ]
                for (delta, ht, wt, sbp, dbp, hr, temp) in readings:
                    rec_at = today + timedelta(days=delta)
                    await conn.execute(
                        text("""
                            INSERT INTO patient_vitals
                                (id, patient_id, recorded_by,
                                 height_cm, weight_kg,
                                 blood_pressure_systolic, blood_pressure_diastolic,
                                 heart_rate, temperature_celsius,
                                 recorded_at, created_at)
                            VALUES
                                (:id, :pid, :rby,
                                 :ht, :wt,
                                 :sbp, :dbp,
                                 :hr, :temp,
                                 :rat, :rat)
                            ON CONFLICT (id) DO NOTHING
                        """),
                        {
                            "id":   str(uuid.uuid4()),
                            "pid":  patient_id,
                            "rby":  doctor_id,
                            "ht":   ht, "wt": wt,
                            "sbp":  sbp, "dbp": dbp,
                            "hr":   hr, "temp": temp,
                            "rat":  rec_at,
                        },
                    )
                    total += 1
        print(f"  [vitals] Seeded {total} vitals readings across {len(PATIENTS)} patients.")
    finally:
        await vitals_engine.dispose()
