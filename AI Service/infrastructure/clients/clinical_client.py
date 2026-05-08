import httpx
from infrastructure.config import get_settings
from Domain.interfaces import IClinicalClient
from Domain.entities import PatientContext
import logging

logger = logging.getLogger(__name__)


class ClinicalClient(IClinicalClient):
    """HTTP client for clinical_service + patient_service. Returns domain entities, not raw dicts."""

    def __init__(self):
        s = get_settings()
        self._clinical_base  = s.CLINICAL_SERVICE_URL
        self._patient_base   = s.PATIENT_SERVICE_URL
        self._timeout        = s.INTERNAL_HTTP_TIMEOUT

    async def get_patient_context(
        self,
        patient_id:  str,
        x_user_id:   str,
        x_user_role: str,
    ) -> PatientContext:
        """
        Fetches rich patient context by combining two internal calls:
          1. clinical_service  GET /patients/{id}/summary  → diagnoses, medications, allergies, vitals
          2. patient_service   GET /internal/patients/{id}/full-context → profile, health_background

        Falls back gracefully on any error so the AI pipeline is never blocked.
        """
        headers = {"X-User-Id": x_user_id, "X-User-Role": x_user_role}

        # ── Defaults ──────────────────────────────────────────────
        full_name   = "Patient"
        age         = None
        gender      = None
        active_diag = []
        current_med = []
        allergies   = ""
        chronic     = ""
        blood_type  = None
        height_cm   = None
        weight_kg   = None
        blood_press = None
        heart_rate  = None

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            # ── 1. Clinical Service: diagnoses, medications, allergies, vitals ──
            try:
                resp = await client.get(
                    f"{self._clinical_base}/patients/{patient_id}/summary",
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()

                # Clinical Service returns the DTO directly (no "data" wrapper)
                active_diag = [
                    d["diagnosis_name"]
                    for d in data.get("diagnoses", [])
                    if d.get("status") == "active"
                ]
                current_med = [
                    f"{m['drug_name']} {m.get('dosage', '')}".strip()
                    for m in data.get("medications", [])
                    if m.get("status") == "active"
                ]
                raw_allergies = data.get("allergies", [])
                if isinstance(raw_allergies, list):
                    allergies = ", ".join(str(a) for a in raw_allergies if a)
                elif isinstance(raw_allergies, str):
                    allergies = raw_allergies

                vitals = data.get("vitals_latest") or {}
                if vitals:
                    height_cm  = vitals.get("height_cm")
                    weight_kg  = vitals.get("weight_kg")
                    blood_press = vitals.get("blood_pressure")
                    heart_rate  = vitals.get("heart_rate_bpm")

            except Exception as e:
                logger.warning("clinical_client: clinical_service fallback for %s: %s", patient_id, e)

            # ── 2. Patient Service: profile + health_background ──
            try:
                resp2 = await client.get(
                    f"{self._patient_base}/internal/patients/{patient_id}/full-context",
                    headers=headers,
                )
                resp2.raise_for_status()
                pdata = resp2.json()

                profile = pdata.get("profile", {}) or {}
                health  = pdata.get("health_background", {}) or {}

                full_name = profile.get("full_name") or full_name
                gender    = profile.get("gender") or gender

                dob = profile.get("date_of_birth")
                if dob:
                    from datetime import date
                    birth = date.fromisoformat(dob)
                    age   = (date.today() - birth).days // 365

                blood_type = health.get("blood_type") or blood_type

                # Use health_background vitals as fallback when Clinical Service had none
                if height_cm is None:
                    height_cm = health.get("height_cm")
                if weight_kg is None:
                    weight_kg = health.get("weight_kg")

                # allergies & chronic_conditions from health_background (override if empty)
                if not allergies:
                    raw = health.get("allergies") or ""
                    allergies = ", ".join(raw) if isinstance(raw, list) else str(raw)
                chronic_raw = health.get("chronic_conditions") or ""
                chronic = ", ".join(chronic_raw) if isinstance(chronic_raw, list) else str(chronic_raw)

                # Vitals embedded in profile take priority over health_background static values
                pvitals = profile.get("vital_signs") or {}
                if pvitals:
                    height_cm   = pvitals.get("height_cm")   or height_cm
                    weight_kg   = pvitals.get("weight_kg")   or weight_kg
                    blood_press = pvitals.get("blood_pressure") or blood_press
                    heart_rate  = pvitals.get("heart_rate_bpm") or heart_rate

            except Exception as e:
                logger.warning("clinical_client: patient_service fallback for %s: %s", patient_id, e)

            # ── 3. Recent clinical notes (last 5) ──────────────────────────
            recent_notes: list[str] = []
            try:
                resp3 = await client.get(
                    f"{self._clinical_base}/patients/{patient_id}/notes?limit=5",
                    headers=headers,
                )
                resp3.raise_for_status()
                notes_data = resp3.json()
                raw_notes = notes_data.get("notes", notes_data) if isinstance(notes_data, dict) else notes_data
                if isinstance(raw_notes, list):
                    recent_notes = [str(n.get("content", ""))[:300] for n in raw_notes if n.get("content")]
            except Exception as e:
                logger.warning("clinical_client: notes fallback for %s: %s", patient_id, e)

        return PatientContext(
            patient_id=patient_id,
            full_name=full_name,
            age=age,
            gender=gender,
            active_diagnoses=active_diag,
            current_medications=current_med,
            allergies=allergies,
            chronic_conditions=chronic,
            blood_type=blood_type,
            height_cm=height_cm,
            weight_kg=weight_kg,
            blood_pressure=blood_press,
            heart_rate_bpm=heart_rate,
            recent_notes=recent_notes,
        )
