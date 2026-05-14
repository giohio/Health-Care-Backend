"""
TriageSessionService — manages the lifecycle of a triage conversation session.

Responsibilities:
  • Create a new session when a patient starts chatting.
  • Load an existing session and validate access rights.
  • Persist completed turns (patient message + AI response).
  • Auto-transition status after the AI issues its recommendation ([R]).
  • Provide doctor review actions: confirm or refer to General Medicine.
  • Generate a clinical summary for doctor review (on-demand, no DB write).
"""

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from Domain.entities import TriageSession
from Domain.enums import Department, TriageSessionStatus
from Domain.interfaces.triage_session_repository import ITriageSessionRepository

if TYPE_CHECKING:
    from Domain.interfaces import ILLMClient

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
#  Custom exceptions
# ──────────────────────────────────────────────────────────────


class TriageSessionNotFound(Exception):
    def __init__(self, session_id: str):
        super().__init__(f"Triage session {session_id!r} not found")


class TriageSessionAccessDenied(Exception):
    """Raised when a patient tries to access another patient's session."""


# ──────────────────────────────────────────────────────────────
#  Urgency / department helpers
# ──────────────────────────────────────────────────────────────

_ROUTINE_KEYWORDS = (
    "routine",
    "thong thuong",
    "thông thường",
)
_PRIORITY_KEYWORDS = (
    "priority",
    "uu tien",
    "ưu tiên",
)
_EMERGENCY_KEYWORDS = (
    "emergency",
    "cap cuu",
    "cấp cứu",
)
_DEFAULT_URGENCY = "Priority"


def _clean_assistant_response(raw: str) -> str:
    """
    Strip internal structured-analysis / reasoning blocks that the LLM prepends
    to its streamed response.

    The model sometimes generates a structured analysis block (e.g.
    "Name: ..., Age: ..., Primary symptom: ..., [Q] reasoning... [Q] question")
    before outputting the actual conversational response.

    Strategy: keep everything from the FIRST [Q] or [R] marker onward,
    since the real response always begins at that point.
    """
    first_q = raw.find("[Q]")
    first_r = raw.find("[R]")
    idx = min(first_q, first_r) if first_q != -1 and first_r != -1 else (first_q if first_q != -1 else first_r)
    if idx == -1:
        return raw
    return raw[idx:].lstrip()

# Maps keyword → Department enum value (longest / most specific listed first)
_DEPT_KEYWORDS: dict[str, str] = {
    "general internal medicine": "General Medicine",
    "internal medicine":         "General Medicine",
    "general medicine":          "General Medicine",
    "noi tong quat":             "General Medicine",
    "nội tổng quát":             "General Medicine",
    "cardiology":                "Cardiology",
    "tim mach":                  "Cardiology",
    "tim mạch":                  "Cardiology",
    "neurology":                 "Neurology",
    "than kinh":                 "Neurology",
    "thần kinh":                 "Neurology",
    "dermatology":               "Dermatology",
    "da lieu":                   "Dermatology",
    "da liễu":                   "Dermatology",
    "ophthalmology":             "Ophthalmology",
    "nhan khoa":                 "Ophthalmology",
    "nhãn khoa":                 "Ophthalmology",
}


def _parse_urgency(text: str) -> str:
    lowered = text.lower()
    if any(kw in lowered for kw in _EMERGENCY_KEYWORDS):
        return "Emergency"
    if any(kw in lowered for kw in _ROUTINE_KEYWORDS):
        return "Routine"
    if any(kw in lowered for kw in _PRIORITY_KEYWORDS):
        return "Priority"
    return _DEFAULT_URGENCY   # safe default when keyword not found


def _parse_department(text: str) -> Optional[str]:
    lowered = text.lower()
    for keyword, dept in _DEPT_KEYWORDS.items():
        if keyword in lowered:
            return dept
    return None


_BOOKING_FILLER_RE = re.compile(
    r"^\s*(yes|yep|yeah|ok|okay|oks|sure|please|pls|confirm|book|book it|go ahead|"
    r"change time|reschedule|thanks|thank you)\b",
    re.IGNORECASE,
)

_SYMPTOM_KEYWORDS = (
    "shortness of breath", "wet cough", "dry cough", "fever", "chills", "cough",
    "breathless", "chest pain", "body aches", "headache", "dizzy", "dizziness",
    "nausea", "vomiting", "diarrhea", "sore throat", "fatigue", "rash",
    "sốt", "ớn lạnh", "ho", "khó thở", "đau ngực", "đau đầu", "chóng mặt",
    "buồn nôn", "nôn", "tiêu chảy", "đau họng", "mệt", "phát ban",
)


def _turn_role(msg: dict) -> str:
    return str(msg.get("role") or "").lower()


def _turn_content(msg: dict) -> str:
    return str(msg.get("content") or "").strip()


def _join_clinical_terms(items: list[str]) -> str:
    clean = [item for item in items if item]
    if not clean:
        return "the reported symptoms"
    if len(clean) == 1:
        return clean[0]
    return ", ".join(clean[:-1]) + f", and {clean[-1]}"


def _infer_fallback_conditions(symptoms: list[str], combined: str) -> list[str]:
    symptom_set = set(symptoms)
    has_cough = any(term in symptom_set for term in ("cough", "wet cough", "dry cough", "ho"))
    has_fever = any(term in symptom_set for term in ("fever", "sốt"))
    has_chills = any(term in symptom_set for term in ("chills", "ớn lạnh"))

    if has_fever and has_cough:
        conditions = ["acute respiratory infection"]
        if has_chills or "body aches" in symptom_set:
            conditions.append("influenza-like illness")
        return conditions
    if has_fever or has_chills:
        return ["acute febrile illness"]
    if "chest pain" in symptom_set or "đau ngực" in symptom_set:
        return ["cardiopulmonary cause of chest pain"]
    if "headache" in symptom_set or "đau đầu" in symptom_set:
        return ["primary headache syndrome"]
    if any(term in combined for term in ("abdominal pain", "stomach pain", "đau bụng")):
        return ["acute gastrointestinal condition"]
    return []


def _infer_fallback_severity(combined: str) -> str:
    if re.search(r"\b(severe|very bad|worst|can't breathe|cannot breathe|không thở|khó thở nhiều|dữ dội)\b", combined):
        return "severe"
    if re.search(r"\b(moderate|medium|vừa|trung bình)\b", combined):
        return "moderate"
    if re.search(r"\b(mild|slight|nhẹ)\b", combined):
        return "mild"
    return "unknown"


def _fallback_clinical_reasoning(symptoms: list[str], duration: str, conditions: list[str]) -> str:
    symptom_text = _join_clinical_terms(symptoms)
    duration_text = "" if not duration or duration == "unknown" else f" lasting {duration}"
    if conditions:
        condition_text = _join_clinical_terms(conditions)
        return (
            f"The combination of {symptom_text}{duration_text} supports concern for {condition_text}. "
            "Persistence of these symptoms warrants clinician assessment rather than continued observation alone."
        )
    return (
        f"The AI recommendation was based on {symptom_text}{duration_text}. "
        "The available conversation is limited, so the doctor should verify severity, red flags, and relevant history."
    )


def _fallback_department_reasoning(department: str, symptoms: list[str], urgency: str) -> str:
    dept = (department or "").lower()
    urgency_part = ""
    if urgency and urgency != "Unknown":
        urgency_part = f" The {urgency.lower()} urgency reflects symptom persistence or potential red flags that need timely review."
    if "general medicine" in dept or "internal medicine" in dept:
        return (
            "General Medicine is appropriate for initial evaluation of systemic symptoms, respiratory examination, "
            "and deciding whether tests or specialist referral are needed."
            + urgency_part
        )
    if "cardiology" in dept:
        return "Cardiology is appropriate because chest or breathing symptoms can require cardiac evaluation." + urgency_part
    if "neurology" in dept:
        return "Neurology is appropriate when headache, dizziness, weakness, or other neurologic symptoms need specialist assessment." + urgency_part
    if "ophthalmology" in dept:
        return "Ophthalmology is appropriate when eye or visual symptoms require focused examination." + urgency_part
    if "dermatology" in dept:
        return "Dermatology is appropriate when skin symptoms require focused assessment." + urgency_part
    symptom_text = _join_clinical_terms(symptoms)
    return f"The department recommendation is based on {symptom_text} and should be confirmed by the reviewing doctor." + urgency_part


def _summary_fallback_from_session(session: TriageSession, _reason: str = "") -> dict:
    patient_messages = [
        _turn_content(m)
        for m in (session.messages or [])
        if _turn_role(m) in ("user", "patient") and _turn_content(m)
    ]
    clinical_messages = [
        msg for msg in patient_messages
        if len(msg) >= 8 and not _BOOKING_FILLER_RE.search(msg)
    ]
    patient_description = clinical_messages[0] if clinical_messages else (patient_messages[0] if patient_messages else "")
    chief_complaint = patient_description or "Summary unavailable"

    combined = " ".join(clinical_messages).lower()
    reported_symptoms = []
    for kw in _SYMPTOM_KEYWORDS:
        if kw == "cough" and any(s in reported_symptoms for s in ("wet cough", "dry cough")):
            continue
        if kw in combined and kw not in reported_symptoms:
            reported_symptoms.append(kw)

    duration = "unknown"
    duration_match = re.search(
        r"\b(?:for\s+)?(?:about\s+|around\s+|maybe\s+)?(\d+\s*(?:day|days|week|weeks|month|months)|a\s+week|one\s+week|today|yesterday)\b",
        combined,
    )
    if duration_match:
        duration = duration_match.group(1)

    recommended_department = session.suggested_department or "Unknown"
    urgency_level = session.urgency_level or "Unknown"
    suspected_conditions = _infer_fallback_conditions(reported_symptoms, combined)
    severity = _infer_fallback_severity(combined)

    return {
        "chief_complaint":        chief_complaint,
        "reported_symptoms":      reported_symptoms,
        "duration":               duration,
        "severity":               severity,
        "suspected_conditions":   suspected_conditions,
        "department_reasoning":   _fallback_department_reasoning(recommended_department, reported_symptoms, urgency_level),
        "recommended_department": recommended_department,
        "urgency_level":          urgency_level,
        "patient_description":    patient_description,
        "clinical_reasoning":     _fallback_clinical_reasoning(reported_symptoms, duration, suspected_conditions),
    }


def _summary_value_missing(value) -> bool:
    return value is None or value == "" or value == []


class TriageSessionService:

    def __init__(self, repo: ITriageSessionRepository):
        self._repo = repo

    # ── Create ────────────────────────────────────────────────

    async def start_session(self, patient_id: str) -> TriageSession:
        """Create a new empty session for a patient."""
        entity = TriageSession(
            id         = str(uuid.uuid4()),
            patient_id = patient_id,
            status     = TriageSessionStatus.ACTIVE,
            messages   = [],
        )
        return await self._repo.save(entity)

    # ── Load ──────────────────────────────────────────────────

    async def load_session(
        self,
        session_id:   str,
        requester_id: str,
        role:         str,
    ) -> TriageSession:
        """
        Fetch an existing session, enforcing ownership for patient role.
        Doctors (and admins) can access any session.
        """
        session = await self._repo.get_by_id(session_id)
        if not session:
            raise TriageSessionNotFound(session_id)
        if role == "patient" and session.patient_id != requester_id:
            raise TriageSessionAccessDenied(
                f"Patient {requester_id!r} cannot access session {session_id!r}"
            )
        return session

    # ── Persist a completed conversation turn ─────────────────

    async def _publish_triage_completed(self, session: TriageSession) -> None:
        """Publish triage.completed event to RabbitMQ for Notification Service."""
        try:
            from infrastructure.publishers import get_triage_event_publisher
            publisher = get_triage_event_publisher()
            await publisher.publish(
                routing_key="triage.completed",
                payload={
                    "session_id": session.id,
                    "patient_id": session.patient_id,
                    "urgency_level": session.urgency_level,
                    "suggested_department": session.suggested_department,
                    "final_department": session.final_department,
                    "status": session.status.value if hasattr(session.status, "value") else session.status,
                    "doctor_id": session.doctor_id,
                },
            )
        except Exception as e:
            logger.warning("Failed to publish triage.completed for session %s: %s", session.id, e)

    async def finish_turn(
        self,
        session_id:        str,
        patient_message:   str,
        assistant_response: str,
        is_recommendation: bool,
        *,
        _entity: TriageSession | None = None,
    ) -> TriageSession:
        """
        Append both the patient message and the AI response to the session,
        then auto-transition status when AI issued a recommendation.

        Pass _entity directly when the session is already loaded (avoids a
        redundant DB round-trip that can race with the streaming generator in
        SQLAlchemy 2.0 async).  If _entity is None the method falls back to
        re-loading by session_id.
        """
        session = _entity if _entity is not None else await self._repo.get_by_id(session_id)
        if not session:
            logger.warning("finish_turn: session %r not found, skipping persist", session_id)
            return TriageSession(
                id=session_id, patient_id="", status=TriageSessionStatus.ABANDONED
            )

        # Strip internal structured-analysis blocks before persisting.
        # These blocks pollute the history and cause the model to echo them.
        clean_response = _clean_assistant_response(assistant_response)
        messages = list(session.messages)
        messages.append({"role": "user",      "content": patient_message})
        messages.append({"role": "assistant", "content": clean_response})
        session.messages = messages

        if is_recommendation:
            # Use the CLEAN response for parsing urgency/department, not the raw one.
            urgency = _parse_urgency(clean_response)
            dept    = _parse_department(clean_response)
            session.urgency_level        = urgency
            session.suggested_department = dept
            session.completed_at         = datetime.now(tz=timezone.utc)
            if urgency == "Routine":
                session.status = TriageSessionStatus.AUTO_CONFIRMED
            else:
                session.status = TriageSessionStatus.PENDING_REVIEW
            # Publish triage.completed event for Notification Service
            await self._publish_triage_completed(session)
        # else: status stays ACTIVE

        return await self._repo.save(session)

    # ── Doctor actions ────────────────────────────────────────

    async def doctor_confirm(
        self,
        session_id: str,
        doctor_id:  str,
        notes:      Optional[str] = None,
    ) -> TriageSession:
        """Doctor agrees with AI suggestion; status → DOCTOR_CONFIRMED."""
        session = await self._repo.get_by_id(session_id)
        if not session:
            raise TriageSessionNotFound(session_id)

        session.status           = TriageSessionStatus.DOCTOR_CONFIRMED
        session.doctor_id        = doctor_id
        session.final_department = session.suggested_department
        session.doctor_notes     = notes
        session.completed_at     = datetime.now(tz=timezone.utc)
        return await self._repo.save(session)

    async def doctor_refer_internal(
        self,
        session_id: str,
        doctor_id:  str,
        notes:      Optional[str] = None,
    ) -> TriageSession:
        """Doctor is unsure; redirect patient to General Medicine."""
        session = await self._repo.get_by_id(session_id)
        if not session:
            raise TriageSessionNotFound(session_id)

        session.status           = TriageSessionStatus.REFERRED_INTERNAL
        session.doctor_id        = doctor_id
        session.final_department = "General Medicine"
        session.doctor_notes     = notes
        session.completed_at     = datetime.now(tz=timezone.utc)
        return await self._repo.save(session)

    # ── Queries ───────────────────────────────────────────────

    async def list_sessions(
        self,
        requester_id:  str,
        role:          str,
        status_filter: Optional[str] = None,
    ) -> list[TriageSession]:
        if role == "patient":
            return await self._repo.list_by_patient(requester_id)
        return await self._repo.list_all(status_filter)

    async def get_session(
        self,
        session_id:   str,
        requester_id: str,
        role:         str,
    ) -> TriageSession:
        return await self.load_session(session_id, requester_id, role)

    # ── AI clinical summary (doctor/admin only) ───────────────

    async def generate_summary(
        self,
        session_id:   str,
        requester_id: str,
        role:         str,
        llm_client:   "ILLMClient",
    ) -> dict:
        """
        Generate an on-demand clinical summary of a triage session for doctor review.
        Returns a dict matching TRIAGE_SUMMARY_SCHEMA.
        Raises TriageSessionAccessDenied if a patient tries to call this.
        """
        from Domain.prompts import (
            TRIAGE_SUMMARY_SCHEMA,
            TRIAGE_SUMMARY_SYSTEM_PROMPT,
            build_triage_summary_prompt,
        )

        if role not in ("doctor", "admin"):
            raise TriageSessionAccessDenied()

        session = await self._repo.get_by_id(session_id)
        if not session:
            raise TriageSessionNotFound(session_id)

        # Minimal fallback when there is nothing useful to summarise
        if not session.messages or not session.suggested_department:
            return _summary_fallback_from_session(
                session,
                "The triage conversation was too short to extract a complete AI summary.",
            )

        user_prompt = build_triage_summary_prompt(
            messages=session.messages,
            recommended_department=session.suggested_department or "",
            urgency_level=session.urgency_level or "",
        )

        result = await llm_client.complete_structured(
            system_prompt=TRIAGE_SUMMARY_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_schema=TRIAGE_SUMMARY_SCHEMA,
            temperature=0.1,
            max_tokens=1024,
        )

        if not result:
            return _summary_fallback_from_session(
                session,
                "The AI summary model did not return structured output, so this summary was generated from the conversation history.",
            )

        # Ensure all required keys are present (LLM may omit optional fields)
        defaults = {
            "chief_complaint":        "",
            "reported_symptoms":      [],
            "duration":               "unknown",
            "severity":               "unknown",
            "suspected_conditions":   [],
            "department_reasoning":   "",
            "recommended_department": session.suggested_department or "",
            "urgency_level":          session.urgency_level or "",
            "patient_description":     "",
            "clinical_reasoning":     "",
        }
        defaults.update(result)
        fallback = None
        for key in (
            "chief_complaint",
            "reported_symptoms",
            "duration",
            "severity",
            "suspected_conditions",
            "department_reasoning",
            "patient_description",
            "clinical_reasoning",
        ):
            if _summary_value_missing(defaults.get(key)):
                if fallback is None:
                    fallback = _summary_fallback_from_session(session)
                defaults[key] = fallback[key]
        return defaults
