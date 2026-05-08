from __future__ import annotations
import json
import logging
import re
import time
from datetime import date, timedelta

from typing import AsyncGenerator, Optional
from Domain.entities import ConversationTurn, SymptomCheckRequest
from Domain.prompts import (
    build_triage_messages,
    _detect_language,
    _detect_booking_mode,
    _BOOKING_INTENT_KEYWORDS,
    _EMERGENCY_MARKERS,
    AI_DISCLAIMER_VI,
    AI_DISCLAIMER_EN,
    build_specialties_extraction_prompt,
    SPECIALTIES_SCHEMA,
    _SPECIALTIES_EXTRACTION_SYSTEM,
)
from Domain.interfaces import ILLMClient, IClinicalClient, IRetriever
from Domain.interfaces.triage_state_repository import ITriageStateRepository
from infrastructure.llm.tools import TOOLS


_SPECIALTY_MAP: dict[str, str] = {
    "Internal Medicine":         "General Medicine",
    "General Internal Medicine": "General Medicine",
    "Ear Nose Throat":           "ENT",
    "Ear, Nose, and Throat":     "ENT",
    "Otolaryngology":            "ENT",
    "Eye":                       "Ophthalmology",
    "Ophthalmics":               "Ophthalmology",
    "Surgery":                   "General Surgery",
    "Paediatrics":               "Pediatrics",
    "Paediatric":                "Pediatrics",
    "Child":                     "Pediatrics",
    "Respiratory":               "General Medicine",
    "Nephrology":                "General Medicine",
    "Hematology":                "General Medicine",
    "Endocrinology":             "General Medicine",
}
_ALLOWED_SPECIALTIES = {
    "Cardiology",
    "Neurology",
    "Pediatrics",
    "General Medicine",
    "General Surgery",
    "Dermatology",
    "ENT",
    "Ophthalmology",
}

_booking_ctx: dict[str, str] = {}


def _normalize_specialty(spec: str) -> str:
    """Canonicalize a specialty name: apply mapping, fall back to General Medicine."""
    return _SPECIALTY_MAP.get(spec, spec if spec in _ALLOWED_SPECIALTIES else "General Medicine")


# ── Booking-availability bypass helpers ───────────────────────────────────────

_SPECIALTY_KEYWORDS_EN = [
    "Cardiology",
    "Neurology",
    "Pediatrics",
    "General Medicine",
    "General Surgery",
    "Dermatology",
    "ENT",
    "Ophthalmology",
]
_SPECIALTY_KEYWORDS_VI = [
    "Tim mạch",       # Cardiology
    "Thần kinh",      # Neurology
    "Nhi khoa",       # Pediatrics
    "Đa khoa",        # General Medicine
    "Nội khoa",       # General Medicine alias
    "Ngoại khoa",     # General Surgery
    "Da liễu",        # Dermatology
    "Tai mũi họng",   # ENT
    "Nhãn khoa",      # Ophthalmology
    "Mắt",            # Ophthalmology alias
]
_SPECIALTY_KEYWORDS = _SPECIALTY_KEYWORDS_EN  # legacy alias — kept for backward compat

# Injected at the end of every non-emergency [R] if the model forgets to ask
_BOOKING_OFFER_EN = "\nWould you like me to help you book an appointment? If so, just let me know your preferred date and time."

# Signatures that identify a slot-listing [Q] response (produced by booking bypass)
_SLOT_LISTING_SIGNATURES = (
    "I found", "opening with", "options for",
    "no available slots", "Shall I confirm",
    "would that work",
)

# Keywords indicating the patient is confirming/selecting a slot
_CONFIRMATION_KEYWORDS = frozenset([
    "yes", "yep", "yeah", "sure", "ok", "okay", "confirm", "go ahead",
    "1", "2", "3", "(1)", "(2)", "(3)", "option 1", "option 2", "option 3",
    "first", "second", "third", "please", "book it", "do it", "proceed",
    "that works", "sounds good", "perfect", "great", "that one",
])

# NOTE: _pending_slots and _recent_recommendation were previously module-level dicts.
# They are now stored in Redis via ITriageStateRepository to support multi-worker
# deployments and survive process restarts. See infrastructure/repositories/redis_triage_state.py.


def _get_next_weekday_str() -> str:
    """Return the nearest upcoming weekday (Mon–Fri) as YYYY-MM-DD."""
    d = date.today() + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d.strftime("%Y-%m-%d")


_WEEKDAY_NAMES_EN = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

def _parse_date_from_message(text: str) -> str | None:
    """
    Extract a date from natural language like:
      - "next wednesday", "next friday"
      - "tomorrow"
      - bare weekday ("wednesday")
    Returns YYYY-MM-DD or None if no date found.
    """
    today = date.today()
    lower = text.lower().strip()

    # "tomorrow"
    if re.search(r"\btomorrow\b", lower):
        d = today + timedelta(days=1)
        return d.strftime("%Y-%m-%d")

    # "next <weekday>" in English
    m = re.search(r"\bnext\s+(" + "|".join(_WEEKDAY_NAMES_EN.keys()) + r")\b", lower)
    if m:
        target_wd = _WEEKDAY_NAMES_EN[m.group(1)]
        days_ahead = (target_wd - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        if days_ahead <= (6 - today.weekday()):
            days_ahead += 7
        d = today + timedelta(days=days_ahead)
        return d.strftime("%Y-%m-%d")

    # Bare English weekday (nearest upcoming, including today)
    for name, wd in _WEEKDAY_NAMES_EN.items():
        if re.search(r"\b" + re.escape(name) + r"\b", lower):
            days_ahead = (wd - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7  # if today is that weekday, go to next occurrence
            d = today + timedelta(days=days_ahead)
            return d.strftime("%Y-%m-%d")

    return None


def _parse_time_preference(text: str) -> str | None:
    """
    Extract a time preference like "8:00", "8h", "8h30", "8 am", "14:00".
    Returns "HH:MM" (24-hour) or None.
    """
    lower = text.lower()

    # e.g. "8h30", "8h", "14h00"
    m = re.search(r"\b(\d{1,2})h(\d{2})?\b", lower)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        if 0 <= hour <= 23:
            return f"{hour:02d}:{minute:02d}"

    # e.g. "8:00", "14:30"
    m = re.search(r"\b(\d{1,2}):(\d{2})\b", lower)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        if 0 <= hour <= 23:
            return f"{hour:02d}:{minute:02d}"

    # e.g. "8 am", "10am", "3 pm"
    m = re.search(r"\b(\d{1,2})\s*(am|pm)\b", lower)
    if m:
        hour = int(m.group(1))
        if m.group(2) == "pm" and hour != 12:
            hour += 12
        elif m.group(2) == "am" and hour == 12:
            hour = 0
        return f"{hour:02d}:00"

    return None


def _next_weekday_after(date_str: str) -> str:
    """Return the weekday after date_str, skipping Sat/Sun."""
    from datetime import datetime
    d = datetime.strptime(date_str, "%Y-%m-%d").date() + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def _extract_department_from_history(history) -> str:
    """Extract the last recommended specialty/department from conversation history."""
    all_kws = _SPECIALTY_KEYWORDS_EN + _SPECIALTY_KEYWORDS_VI
    for turn in reversed(history):
        if turn.role != "patient" and turn.content.lstrip().startswith("[R]"):
            text_lower = turn.content.lower()
            for kw in all_kws:
                if kw.lower() in text_lower:
                    return kw
    return "General Medicine"


def _detect_confirmation_mode(request) -> bool:
    """
    Return True if the last assistant message was a slot-listing [Q] produced
    by the booking bypass AND the patient's message is a selection/confirmation.
    """
    _log = logging.getLogger(__name__)
    if not request.conversation_history:
        return False
    last_assistant = next(
        (t for t in reversed(request.conversation_history) if t.role != "patient"),
        None,
    )
    if last_assistant is None:
        return False
    content = last_assistant.content
    if not any(sig in content for sig in _SLOT_LISTING_SIGNATURES):
        return False
    msg_lower = request.symptoms.lower().strip()
    matched = any(kw in msg_lower for kw in _CONFIRMATION_KEYWORDS)
    _log.warning("CONFIRMATION_MODE: msg=%r matched=%s", msg_lower[:60], matched)
    return matched


def _parse_slot_selection(patient_msg: str, slots: list[dict]) -> dict | None:
    """Map patient's confirmation message to a specific slot. Defaults to slot[0]."""
    if not slots:
        return None
    msg = patient_msg.lower().strip()
    patterns_by_index = [
        (0, [r'\b1\b', r'\(1\)', r'option\s*1', r'\bfirst\b']),
        (1, [r'\b2\b', r'\(2\)', r'option\s*2', r'\bsecond\b']),
        (2, [r'\b3\b', r'\(3\)', r'option\s*3', r'\bthird\b']),
    ]
    for idx, pats in patterns_by_index:
        if idx < len(slots) and any(re.search(p, msg) for p in pats):
            return slots[idx]
    for slot in slots:
        name = slot.get("doctor_name", "")
        if name:
            last_name = name.split()[-1].lower()
            if last_name and last_name in msg:
                return slot
    m = re.search(r'\b(\d{1,2}):(\d{2})\b', msg)
    if m:
        target = f"{int(m.group(1)):02d}:{m.group(2)}"
        for slot in slots:
            if slot.get("start_time", "")[:5] == target:
                return slot
    return slots[0]


def _format_confirmation_en(result: dict, slot: dict) -> str:
    if result.get("status") == "error":
        return (
            f"Sorry, I wasn't able to complete the booking: "
            f"{result.get('message', 'Unknown error')}. "
            f"Please try again or contact the clinic directly."
        )
    name = slot.get("doctor_name", "your doctor")
    t = slot.get("start_time", "")[:5]
    d = result.get("date", "")
    if result.get("status") == "pending_review":
        return (
            f"Booking request submitted!\n"
            f"Doctor: {name}\n"
            f"Date: {d} at {t}\n"
            f"Your request is now awaiting doctor review. "
            f"You will be notified once the doctor confirms your appointment."
        )
    appt_id = result.get("appointment_id", "")
    return (
        f"Appointment confirmed!\n"
        f"Doctor: {name}\n"
        f"Date: {d} at {t}\n"
        f"Booking ID: {appt_id}\n"
        f"You'll receive a confirmation and payment instructions via the app."
    )


def _sort_slots_by_time_pref(slots: list, time_pref: str | None) -> list:
    """Re-order slots so the one closest to time_pref appears first."""
    if not time_pref or not slots:
        return slots
    try:
        pref_hour, pref_min = map(int, time_pref.split(":"))
        pref_minutes = pref_hour * 60 + pref_min
    except ValueError:
        return slots

    def _dist(s):
        t = s.get("start_time", "00:00")[:5]
        try:
            h, m = map(int, t.split(":"))
            return abs(h * 60 + m - pref_minutes)
        except ValueError:
            return 9999

    return sorted(slots, key=_dist)


def _format_availability_en(result: dict, date_str: str, time_pref: str | None = None) -> str:
    """Format check_availability result in English per the 4-case template."""
    status = result.get("status")

    if status == "unsupported_department":
        requested = result.get("department") or "this department"
        supported = result.get("supported_departments") or sorted(_ALLOWED_SPECIALTIES)
        supported_str = ", ".join(supported)
        return (
            f"{requested} is currently not supported for booking. "
            f"Please choose one of our available departments: {supported_str}."
        )

    if status == "no_doctors":
        mapped = result.get("department") or "This department"
        return (
            f"{mapped} is currently unavailable for booking because we do not have active doctors there yet. "
            f"Please choose another available department."
        )

    if status == "error":
        return (
            "I could not check appointment availability right now due to a system issue. "
            "Please try again in a moment."
        )

    if status in ("no_slots", "no_slots_for_date") or not result.get("slots"):
        next_date = _next_weekday_after(date_str)
        return (
            f"There are no available slots on {date_str} for this department. "
            f"Would you like to try {next_date} instead?"
        )
    slots = _sort_slots_by_time_pref(result["slots"], time_pref)
    doctors: dict[str, list] = {}
    for s in slots:
        name = s.get("doctor_name", "Doctor")
        doctors.setdefault(name, []).append(s)

    if len(doctors) == 1:
        doctor_name = next(iter(doctors))
        times = [s["start_time"][:5] for s in doctors[doctor_name]]
        if len(times) == 1:
            return (
                f"I found an opening with {doctor_name} at {times[0]} on {date_str}. "
                f"Shall I confirm this booking?"
            )
        times_str = ", ".join(times)
        suggest = times[0]
        suffix = f" (closest to {time_pref})" if time_pref else ""
        return (
            f"{doctor_name} has {len(times)} openings on {date_str}: {times_str}. "
            f"I'd suggest {suggest}{suffix} — would that work, or would you prefer a different time?"
        )
    # Multiple doctors — show up to 3
    lines = [f"I found {min(len(doctors), 3)} options for {date_str}:"]
    for i, (name, slots_list) in enumerate(list(doctors.items())[:3], 1):
        t = slots_list[0]["start_time"][:5]
        suffix = f"  ← closest to {time_pref}" if (i == 1 and time_pref) else ("  ← recommended" if i == 1 else "")
        lines.append(f"({i}) {name} — {t}{suffix}")
    lines.append("I'd recommend option (1). Which would you prefer, or shall I go with (1)?")
    return "\n".join(lines)


async def _booking_tool_handler(tool_name: str, args: dict) -> dict:
    """
    Dispatch tool calls to booking implementations.
    Injects session context (department, patient_id, session_id) from closure.
    """
    from infrastructure.llm.booking_tools import fn_check_availability, fn_create_appointment

    if tool_name == "check_availability":
        return await fn_check_availability(
            department=args.get("department", ""),
            date=args.get("date", ""),
        )

    if tool_name == "create_appointment":
        # Extract from closure set by SymptomCheckUseCase
        patient_id  = _booking_ctx.get("patient_id", "")
        session_id  = _booking_ctx.get("session_id", "")
        department  = _booking_ctx.get("department", "")
        urgency     = _booking_ctx.get("urgency_level", "Routine")
        return await fn_create_appointment(
            doctor_id=args.get("doctor_id", ""),
            specialty_id=args.get("specialty_id", ""),
            date=args.get("date", ""),
            time=args.get("time", ""),
            patient_id=patient_id,
            session_id=session_id,
            department=department,
            urgency_level=urgency,
            doctor_name=args.get("doctor_name", ""),
        )

    return {"error": f"Unknown tool: {tool_name}"}


class SymptomCheckUseCase:
    """
    Tier 1: Conversational triage agent.
    ...
    """

    SPECIALTIES_MARKER  = "[SPECIALTIES_MARKER]"
    APPOINTMENT_MARKER   = "[APPOINTMENT_MARKER]"
    _log = logging.getLogger(__name__)

    def __init__(
        self,
        llm:       ILLMClient,
        clinical:  IClinicalClient,
        retriever: Optional[IRetriever] = None,
        state:     Optional[ITriageStateRepository] = None,
    ):
        self._llm       = llm
        self._clinical  = clinical
        self._retriever = retriever
        self._state     = state

    async def execute(
        self,
        request:     SymptomCheckRequest,
        x_user_id:   str,
        x_user_role: str,
    ) -> AsyncGenerator[str, None]:

        # ── Date-change detection (re-query when patient asks for a different date) ──
        # If pending slots exist and the patient specifies a date that differs from
        # the date already shown, re-query availability for the new date and update.
        _pending_for_date_check = await self._state.get_pending_slots(request.patient_id) if self._state else None
        if _pending_for_date_check:
            # ── No-slots acceptance: patient confirmed "try YYYY-MM-DD instead?" ────
            # When the last response was "no available slots" (no_slots=True),
            # pending["date_str"] already holds the next weekday to try.
            # A bare confirmation keyword means "yes, try that date".
            if _pending_for_date_check.get("no_slots"):
                msg_lower = request.symptoms.lower().strip()
                if any(kw in msg_lower for kw in _CONFIRMATION_KEYWORDS):
                    from infrastructure.llm.booking_tools import fn_check_availability
                    _target_date = _pending_for_date_check["date_str"]
                    _dept = _pending_for_date_check["department"]
                    self._log.warning(
                        "NO-SLOTS ADVANCE: patient=%r trying next date %r dept=%r",
                        request.patient_id, _target_date, _dept,
                    )
                    _new_avail = await fn_check_availability(_dept, _target_date)
                    _status = _new_avail.get("status")
                    if _new_avail.get("slots") and self._state:
                        await self._state.set_pending_slots(request.patient_id, {
                            "slots": _new_avail["slots"],
                            "date_str": _target_date,
                            "department": _dept,
                        })
                    elif self._state and _status in ("no_slots", "no_slots_for_date"):
                        # Still no slots — track retries; stop after 2 attempts
                        _retry = _pending_for_date_check.get("retry_count", 0) + 1
                        if _retry >= 2:
                            # Give up: no available slots across multiple days
                            await self._state.del_pending_slots(request.patient_id)
                            yield (
                                "[Q] I wasn't able to find any available slots for this department "
                                "over the next several days. You can try booking directly from the "
                                "Appointments section or contact the clinic for assistance."
                            )
                            return
                        _next_next = _next_weekday_after(_target_date)
                        await self._state.set_pending_slots(request.patient_id, {
                            "slots": [],
                            "date_str": _next_next,
                            "department": _dept,
                            "no_slots": True,
                            "retry_count": _retry,
                        })
                    yield f"[Q] {_format_availability_en(_new_avail, _target_date)}"
                    return

            _new_date = _parse_date_from_message(request.symptoms)
            if _new_date and _new_date != _pending_for_date_check["date_str"]:
                from infrastructure.llm.booking_tools import fn_check_availability
                _new_time_pref = _parse_time_preference(request.symptoms)
                _dept = _pending_for_date_check["department"]
                self._log.warning(
                    "DATE CHANGE DETECTED: patient=%r %r→%r dept=%r",
                    request.patient_id, _pending_for_date_check["date_str"], _new_date, _dept,
                )
                _new_avail = await fn_check_availability(_dept, _new_date)
                formatter = _format_availability_en
                if _new_avail.get("slots") and self._state:
                    await self._state.set_pending_slots(request.patient_id, {
                        "slots": _new_avail["slots"],
                        "date_str": _new_date,
                        "department": _dept,
                    })
                yield f"[Q] {formatter(_new_avail, _new_date, _new_time_pref)}"
                return

        # ── Confirmation bypass (slot selection → create_appointment) ─────────
        # Runs FIRST: patient already saw slot options and is now confirming.
        if _detect_confirmation_mode(request):
            pending = await self._state.get_pending_slots(request.patient_id) if self._state else None
            if pending:
                from infrastructure.llm.booking_tools import fn_create_appointment
                selected = _parse_slot_selection(request.symptoms, pending["slots"])
                if selected:
                    self._log.warning(
                        "CONFIRMATION BYPASS FIRED: patient=%r doctor=%r time=%r",
                        request.patient_id, selected.get("doctor_name"), selected.get("start_time"),
                    )
                    result = await fn_create_appointment(
                        doctor_id=selected["doctor_id"],
                        specialty_id=selected["specialty_id"],
                        date=pending["date_str"],
                        time=selected["start_time"][:5],
                        patient_id=request.patient_id,
                        session_id=request.session_id or "",
                        department=pending["department"],
                        urgency_level=request.urgency_level or "Routine",
                        doctor_name=selected.get("doctor_name", ""),
                    )
                    # Inject date into result so formatter can use it
                    result["date"] = pending["date_str"]
                lang = _detect_language(request.symptoms)
                formatter = _format_confirmation_en
                yield f"[Q] {formatter(result, selected)}"
                # Emit appointment marker for both confirmed and pending_review states
                if result.get("status") in ("created", "pending_review") and result.get("status") != "error":
                    appt_data = {
                        "status": result.get("status"),
                        "appointment_id": result.get("appointment_id"),
                        "doctor_name": selected.get("doctor_name", ""),
                        "date": pending["date_str"],
                        "start_time": selected.get("start_time", "")[:5],
                        "specialty": pending.get("department", ""),
                    }
                    yield f"{self.APPOINTMENT_MARKER}{json.dumps(appt_data)}{self.APPOINTMENT_MARKER}"
                if self._state:
                    await self._state.del_pending_slots(request.patient_id)
                    # Clear rec cache so post-booking messages ("ok thanks") don't
                    # re-trigger the booking bypass.
                    if result.get("status") in ("created", "pending_review"):
                        await self._state.del_recommendation(request.patient_id)
                return

        # ── Booking-availability bypass (runs BEFORE any LLM/RAG/context calls) ──
        # Primary: [R] in history + booking keyword (standard flow).
        # Fallback: server-side recommendation cache + booking keyword.
        #   Needed because the frontend has a known bug where conversation_history
        #   stops updating past ~4 turns, so [R] is never present in the payload
        #   when the patient later says "book for me".

        # ── Emergency booking intercept ────────────────────────────────────────
        # When the last [R] was an emergency AND the patient asks to book,
        # return a clear rejection message WITHOUT touching the LLM.
        _has_booking_intent = any(kw in request.symptoms.lower() for kw in _BOOKING_INTENT_KEYWORDS)
        if _has_booking_intent and request.conversation_history:
            _last_r_content: str | None = None
            for _t in request.conversation_history:
                if _t.role != "patient" and _t.content.lstrip().startswith("[R]"):
                    _last_r_content = _t.content
            if _last_r_content and any(m in _last_r_content.lower() for m in _EMERGENCY_MARKERS):
                self._log.warning(
                    "EMERGENCY BOOKING INTERCEPT: patient=%r symptoms=%r",
                    request.patient_id, request.symptoms[:60],
                )
                yield (
                    "[Q] Given the severity of your symptoms, waiting for a standard appointment is not safe. "
                    "Please go to the nearest Emergency Room or call emergency services (115) immediately. "
                    "This is a medical emergency — do not delay."
                )
                return

        _recent_rec = await self._state.get_recommendation(request.patient_id) if self._state else None
        _request_session_id = (request.session_id or "").strip()
        _cache_session_id = str((_recent_rec or {}).get("session_id") or "").strip()
        _same_session_cache = bool(
            _recent_rec
            and _request_session_id
            and _cache_session_id
            and _cache_session_id == _request_session_id
        )

        # First-turn direct booking: user says "book for me" with zero history and no
        # prior recommendation cached — go straight to availability instead of asking
        # for symptoms.
        _is_first_turn_booking = (
            _has_booking_intent
            and not request.conversation_history
            and not _request_session_id
        )

        if _detect_booking_mode(request) or (_has_booking_intent and _same_session_cache) or _is_first_turn_booking:
            from infrastructure.llm.booking_tools import fn_check_availability
            # Department priority: explicit field > history extraction > server cache > default
            _hist_dept = _normalize_specialty(_extract_department_from_history(request.conversation_history or []))
            department = (
                request.suggested_department
                or (_hist_dept if _hist_dept != "General Medicine" else None)
                or (_recent_rec["department"] if _recent_rec else None)
                or "General Medicine"
            )
            _from_cache = _same_session_cache and not _detect_booking_mode(request)
            self._log.warning(
                "BOOKING BYPASS FIRED: dept=%r symptoms=%r history_len=%d from_cache=%r first_turn=%r req_sid=%r cache_sid=%r",
                department, request.symptoms[:60],
                len(request.conversation_history or []),
                _from_cache, _is_first_turn_booking,
                _request_session_id, _cache_session_id,
            )
            date_str = _parse_date_from_message(request.symptoms) or _get_next_weekday_str()
            time_pref = _parse_time_preference(request.symptoms)
            availability = await fn_check_availability(department, date_str)
            formatter = _format_availability_en
            # Store slots keyed by patient_id for confirmation bypass on the next turn
            if availability.get("slots"):
                if self._state:
                    await self._state.set_pending_slots(request.patient_id, {
                        "slots": availability["slots"],
                        "date_str": date_str,
                        "department": department,
                    })
                self._log.warning(
                    "PENDING SLOTS STORED: patient=%r count=%d dept=%r date=%r time_pref=%r",
                    request.patient_id, len(availability["slots"]), department, date_str, time_pref,
                )
            elif availability.get("status") in ("no_slots", "no_slots_for_date"):
                # No slots available — store a no-slots sentinel so the next turn
                # can advance to next_date instead of re-querying the same date.
                if self._state:
                    _no_slots_next = _next_weekday_after(date_str)
                    await self._state.set_pending_slots(request.patient_id, {
                        "slots": [],
                        "date_str": _no_slots_next,
                        "department": department,
                        "no_slots": True,
                    })
                    self._log.warning(
                        "NO-SLOTS SENTINEL STORED: patient=%r next_date=%r dept=%r",
                        request.patient_id, _no_slots_next, department,
                    )
            yield f"[Q] {formatter(availability, date_str, time_pref)}"
            return

        context = await self._clinical.get_patient_context(
            request.patient_id, x_user_id, x_user_role
        )

        rag_context = ""
        if self._retriever:
            rag_context = await self._retriever.get_context(
                request.symptoms, department=None, top_k=3
            )

        messages = build_triage_messages(request, context, rag_context=rag_context)

        # Buffer the first few chars to determine turn type ([Q] vs [R])
        # without accumulating the full response.
        prefix: str = ""
        is_recommendation: bool | None = None
        full_response_parts: list[str] = []

        # Build per-request booking context and closure to avoid global mutation race condition.
        _local_ctx = {
            "patient_id":    request.patient_id,
            "session_id":    request.session_id or "",
            "department":    request.suggested_department or "",
            "urgency_level": request.urgency_level or "Routine",
        }

        async def _local_tool_handler(tool_name: str, args: dict) -> dict:
            from infrastructure.llm.booking_tools import fn_check_availability, fn_create_appointment
            if tool_name == "check_availability":
                return await fn_check_availability(
                    department=args.get("department", ""),
                    date=args.get("date", ""),
                )
            if tool_name == "create_appointment":
                return await fn_create_appointment(
                    doctor_id=args.get("doctor_id", ""),
                    specialty_id=args.get("specialty_id", ""),
                    date=args.get("date", ""),
                    time=args.get("time", ""),
                    patient_id=_local_ctx["patient_id"],
                    session_id=_local_ctx["session_id"],
                    department=_local_ctx["department"],
                    urgency_level=_local_ctx["urgency_level"],
                    doctor_name=args.get("doctor_name", ""),
                )
            return {"error": f"Unknown tool: {tool_name}"}

        # Always run with tools so the model can call check_availability /
        # create_appointment at any turn. The system prompt already constrains
        # WHEN to invoke them (only after [R] + patient confirms a date).
        async for chunk in self._llm.stream_with_tools(
            messages=messages,
            tools=TOOLS,
            tool_handler=_local_tool_handler,
            temperature=0.4,
            max_tokens=2048,
        ):
            if is_recommendation is None:
                prefix += chunk
                if len(prefix) >= 4:
                    is_recommendation = prefix.startswith("[R]")
            full_response_parts.append(chunk)
            yield chunk

        # Append disclaimer only on final recommendation turns
        if is_recommendation:
            all_user_text = " ".join(
                t.content for t in (request.conversation_history or []) if t.role == "patient"
            ) + " " + request.symptoms
            lang = _detect_language(all_user_text)
            full_response_so_far = "".join(full_response_parts)
            # Guarantee the booking offer is present — Gemma sometimes forgets it.
            # Never add it for Emergency [R] responses.
            is_emergency = any(m in full_response_so_far.lower() for m in _EMERGENCY_MARKERS)

            # ── EARLY CACHE: set BEFORE complete_structured so that the booking
            # bypass works even if the LLM call is slow / the SSE connection drops
            # before complete_structured returns. ────────────────────────────────
            if not is_emergency:
                _dept_early = _normalize_specialty(_extract_department_from_history([
                    ConversationTurn(role="assistant", content=full_response_so_far)
                ]))
                # Always cache — including General Medicine — so the booking bypass
                # fires even when the LLM recommends a primary-care department.
                if self._state:
                    await self._state.set_recommendation(request.patient_id, {
                        "department": _dept_early,
                        "timestamp": time.time(),
                        "session_id": (request.session_id or "").strip() or None,
                    })
                self._log.warning(
                    "RECOMMENDATION CACHED (early): patient=%r dept=%r",
                    request.patient_id, _dept_early,
                )
            else:
                # Emergency: clear any stale cache immediately
                if self._state:
                    await self._state.del_recommendation(request.patient_id)
                self._log.warning(
                    "RECOMMENDATION CACHE CLEARED (emergency, early): patient=%r",
                    request.patient_id,
                )

            offer_en = "would you like me to help you book"
            _resp_lower = full_response_so_far.lower()
            if not is_emergency:
                if offer_en not in _resp_lower:
                    booking_offer = _BOOKING_OFFER_EN
                    yield booking_offer
                    full_response_parts.append(booking_offer)

            disclaimer = AI_DISCLAIMER_EN
            # Only append if the LLM didn't already include it in its own output.
            # (Some models add a medical disclaimer autonomously; appending again would duplicate it.)
            # Use strip() on both sides so trailing newlines don't cause false negatives.
            if disclaimer.strip().lower() not in full_response_so_far.strip().lower():
                yield f"\n\n{disclaimer}"
                full_response_parts.append(f"\n\n{disclaimer}")

            # Structured extraction: call Groq JSON mode to get specialties list
            full_response = "".join(full_response_parts)
            extraction_prompt = build_specialties_extraction_prompt(messages, full_response)
            result = await self._llm.complete_structured(
                system_prompt=_SPECIALTIES_EXTRACTION_SYSTEM,
                user_prompt=extraction_prompt,
                response_schema=SPECIALTIES_SCHEMA,
                temperature=0.1,
                max_tokens=256,
            )
            specialties: list[str] = [
                _normalize_specialty(s) for s in result.get("specialties", [])
            ]
            if specialties:
                # Refine cache BEFORE yield — guarantees the cache is set even if
                # the client disconnects the moment it receives the specialties event.
                # Only for non-emergency (emergency cache was already cleared above).
                if not is_emergency and self._state:
                    await self._state.set_recommendation(request.patient_id, {
                        "department": specialties[0],
                        "timestamp": time.time(),
                        "session_id": (request.session_id or "").strip() or None,
                    })
                    self._log.warning(
                        "RECOMMENDATION CACHED (refined): patient=%r dept=%r",
                        request.patient_id, specialties[0],
                    )
                yield f"{self.SPECIALTIES_MARKER}{json.dumps(specialties)}{self.SPECIALTIES_MARKER}"

