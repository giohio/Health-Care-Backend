"""
HTTP client for Appointment Service.
Provides availability checking and appointment creation for the AI triage pipeline.
"""
import httpx
import logging
from typing import Any

from infrastructure.config import get_settings

logger = logging.getLogger(__name__)


class AppointmentServiceClient:
    """
    HTTP client for Appointment Service.

    Used by the AI triage pipeline to:
      - check which doctors in a department have available slots
      - create an appointment with AI-referral metadata attached
    """

    # Mapping from AI department keywords → specialty names used by Doctor Service.
    # Keys are lowercase to handle both English keywords and Vietnamese names.
    # Values MUST match the exact specialty names seeded in Doctor Service DB
    # (seed_doctors.py): Internal Medicine, Cardiology, Neurology, Dermatology,
    #   Respiratory, Nephrology, Hematology, Endocrinology, Pediatrics, etc.
    # Specialties not in Doctor Service fall back to "Internal Medicine".
    _DEPT_TO_SPECIALTY: dict[str, str] = {
        # English keywords → exact Doctor Service specialty name
        # Seeded specialties: General Medicine, Cardiology, Neurology, Pediatrics,
        #   General Surgery, Dermatology, ENT, Ophthalmology
        "general medicine":           "General Medicine",
        "internal medicine":          "General Medicine",
        "general internal medicine":  "General Medicine",
        "internal_medicine":          "General Medicine",
        "cardiology":                 "Cardiology",
        "neurology":                  "Neurology",
        "dermatology":                "Dermatology",
        "pediatrics":                 "Pediatrics",
        "general surgery":            "General Surgery",
        "ent":                        "ENT",
        "ophthalmology":              "Ophthalmology",
        # Not seeded → fall back to General Medicine
        "respiratory":                "General Medicine",
        "nephrology":                 "General Medicine",
        "hematology":                 "General Medicine",
        "endocrinology":              "General Medicine",
        "infectious diseases":        "General Medicine",
        "orthopedics":                "General Surgery",
        "rheumatology":               "General Medicine",
        "gastroenterology":           "General Medicine",
        "pulmonology":                "General Medicine",
        # Vietnamese department names (lowercase)
        "tim mach":                   "Cardiology",
        "than kinh":                  "Neurology",
        "da lieu":                    "Dermatology",
        "nhi khoa":                   "Pediatrics",
        "ngoai tong quat":            "General Surgery",
        "tai mui hong":               "ENT",
        "nhan khoa":                  "Ophthalmology",
        "noi tong quat":              "General Medicine",
        "noi tiet":                   "General Medicine",
        "ho hap":                     "General Medicine",
        "than hoc":                   "General Medicine",
        "huyet hoc":                  "General Medicine",
    }

    # Cache: specialty name → UUID, refreshed once per process lifetime
    _SPECIALTY_NAME_TO_ID: dict[str, str] = {}

    _SUPPORTED_DEPARTMENTS: tuple[str, ...] = (
        "Cardiology",
        "Neurology",
        "Pediatrics",
        "General Medicine",
        "General Surgery",
        "Dermatology",
        "ENT",
        "Ophthalmology",
    )

    def __init__(self):
        s = get_settings()
        self._base = getattr(s, "APPOINTMENT_SERVICE_URL", "http://appointment_service:8000")
        self._doctor_base = getattr(s, "DOCTOR_SERVICE_URL", "http://doctor_service:8000")
        self._timeout = getattr(s, "INTERNAL_HTTP_TIMEOUT", 10)

    def resolve_department_to_specialty(self, department: str) -> str | None:
        """
        Resolve external department input to a seeded Doctor Service specialty.
        Returns None when the department is unsupported.
        """
        if not department:
            return None
        specialty_name = self._DEPT_TO_SPECIALTY.get(department.lower().strip())
        if specialty_name in self._SUPPORTED_DEPARTMENTS:
            return specialty_name
        return None

    # ── Availability ────────────────────────────────────────────────────────────

    async def _get_specialty_id_by_name(self, specialty_name: str) -> str | None:
        """
        Resolve specialty name → UUID by calling Doctor Service /specialties.
        Results are cached in _SPECIALTY_NAME_TO_ID.
        """
        if specialty_name in self._SPECIALTY_NAME_TO_ID:
            return self._SPECIALTY_NAME_TO_ID[specialty_name]
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._doctor_base}/specialties")
                if resp.status_code == 200:
                    for spec in resp.json():
                        if spec.get("name", "").lower() == specialty_name.lower():
                            uid = str(spec["id"])
                            self._SPECIALTY_NAME_TO_ID[specialty_name] = uid
                            return uid
                logger.warning(
                    "_get_specialty_id_by_name(%s) returned %s",
                    specialty_name, resp.status_code,
                )
        except Exception as e:
            logger.warning("_get_specialty_id_by_name(%s) error: %s", specialty_name, e)
        return None

    async def get_doctors_by_specialty(self, specialty_name: str) -> list[dict]:
        """
        Return a list of doctors that belong to the given specialty.
        Calls: GET /doctors/specialty/{specialty_id}  (UUID, not name)
        """
        specialty_id = await self._get_specialty_id_by_name(specialty_name)
        if not specialty_id:
            return []
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{self._doctor_base}/doctors/specialty/{specialty_id}",
                )
                if resp.status_code == 200:
                    return resp.json()
                logger.warning(
                    "get_doctors_by_specialty(%s) returned %s: %s",
                    specialty_name, resp.status_code, resp.text[:200],
                )
        except Exception as e:
            logger.warning("get_doctors_by_specialty(%s) error: %s", specialty_name, e)
        return []

    async def get_available_slots(
        self,
        doctor_id: str,
        specialty_id: str,
        appointment_date: str,
    ) -> list[dict]:
        """
        Return available time slots for a specific doctor on a given date.
        Calls: GET /appointments/doctor/{doctor_id}/slots
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{self._base}/appointments/doctor/{doctor_id}/slots",
                    params={
                        "appointment_date": appointment_date,
                        "specialty_id": specialty_id,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("slots", [])
                logger.warning(
                    "get_available_slots(%s, %s) returned %s: %s",
                    doctor_id, appointment_date, resp.status_code, resp.text[:200],
                )
        except Exception as e:
            logger.warning("get_available_slots(%s) error: %s", doctor_id, e)
        return []

    async def check_availability_by_department(
        self,
        department: str,
        appointment_date: str,
    ) -> list[dict]:
        """
        Check available slots across all doctors in the given department.
        Returns a flat list of slot objects enriched with doctor info:
          [{doctor_id, doctor_name, specialty_id, start_time, end_time, is_available}, ...]
        """
        specialty_name = self.resolve_department_to_specialty(department)
        if not specialty_name:
            logger.warning("Unknown department keyword: %s", department)
            return []

        doctors = await self.get_doctors_by_specialty(specialty_name)
        all_slots: list[dict] = []

        for doctor in doctors:
            doctor_id = str(doctor.get("user_id") or doctor.get("id") or "")
            specialty_id = str(doctor.get("specialty_id") or "")
            if not doctor_id or not specialty_id:
                continue

            slots = await self.get_available_slots(doctor_id, specialty_id, appointment_date)
            for slot in slots:
                if slot.get("is_available"):
                    all_slots.append({
                        "doctor_id":    doctor_id,
                        "doctor_name":  doctor.get("full_name", "Bác sĩ"),
                        "specialty_id": specialty_id,
                        "start_time":   slot.get("start_time"),
                        "end_time":     slot.get("end_time"),
                    })

        # Sort by start_time for consistent UX
        all_slots.sort(key=lambda s: s["start_time"])
        return all_slots

    # ── Appointment creation ────────────────────────────────────────────────────

    async def create_appointment(
        self,
        doctor_id: str,
        specialty_id: str,
        appointment_date: str,
        start_time: str,
        patient_id: str,
        triage_session_id: str | None,
        urgency_level: str,
        referred_by_doctor_id: str | None,
        chief_complaint: str | None = None,
    ) -> dict[str, Any]:
        """
        Create an appointment tagged with AI triage metadata.
        Calls: POST /appointments/

        The appointment is created in PENDING_PAYMENT status.
        Payment triggers PaymentPaidConsumer which:
          - Detects ai_referred=True
          - Sets status = PENDING (not auto-confirmed)
          - Notifies the GM doctor for priority review
        """
        payload = {
            "doctor_id": doctor_id,
            "specialty_id": specialty_id,
            "appointment_date": appointment_date,
            "start_time": start_time,
            "appointment_type": "general",
            "chief_complaint": chief_complaint,
            "ai_referred": True,
            "urgency_level": urgency_level,
        }
        if triage_session_id:
            payload["triage_session_id"] = triage_session_id
        if referred_by_doctor_id:
            payload["referred_by_doctor_id"] = referred_by_doctor_id

        headers = {
            "X-User-Id": patient_id,
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base}/appointments/",
                    json=payload,
                    headers=headers,
                )
                if resp.status_code in (200, 201):
                    return resp.json()
                logger.warning(
                    "create_appointment failed: %s %s",
                    resp.status_code, resp.text[:300],
                )
                return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        except Exception as e:
            logger.error("create_appointment error: %s", e)
            return {"error": str(e)}
