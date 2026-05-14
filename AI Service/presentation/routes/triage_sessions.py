import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Body
from pydantic import BaseModel

from Application.triage_session import (
    TriageSessionAccessDenied,
    TriageSessionNotFound,
    TriageSessionService,
)
from Application.booking_use_case import BookingUseCase
from infrastructure.database.session import AsyncSessionLocal
from infrastructure.repositories.triage_session_repository import TriageSessionRepository
from infrastructure.clients.appointment_service_client import AppointmentServiceClient
from infrastructure.clients.patient_service_client import PatientServiceClient
from infrastructure.llm.woku_client import WokuClient
from presentation.schema import (
    DoctorConfirmInput,
    DoctorReferInput,
    TriageSessionListResponse,
    TriageSessionResponse,
    TriageSummaryResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/triage-sessions", tags=["AI - Triage Sessions"])


# ── Helpers ─────────────────────────────────────────────────────────────────

def _to_response(session, patient_name: str | None = None) -> TriageSessionResponse:
    return TriageSessionResponse(
        id                   = session.id,
        patient_id           = session.patient_id,
        patient_name         = patient_name,
        status               = session.status.value if hasattr(session.status, "value") else session.status,
        messages             = session.messages,
        suggested_department = session.suggested_department,
        urgency_level        = session.urgency_level,
        doctor_id            = session.doctor_id,
        final_department     = session.final_department,
        doctor_notes         = session.doctor_notes,
        created_at           = session.created_at.isoformat() if session.created_at else None,
        updated_at           = session.updated_at.isoformat() if session.updated_at else None,
        completed_at         = session.completed_at.isoformat() if session.completed_at else None,
        appointment_id       = session.appointment_id if hasattr(session, "appointment_id") else None,
        pending_booking      = session.pending_booking if hasattr(session, "pending_booking") else None,
    )


# ── List sessions ────────────────────────────────────────────────────────────

@router.get("", response_model=TriageSessionListResponse)
async def list_triage_sessions(
    status: Optional[str] = Query(default=None, description="Filter by status (doctor only)"),
    x_user_id:   str = Header(...),
    x_user_role: str = Header(...),
):
    """
    List triage sessions.
    - **patient**: returns only their own sessions.
    - **doctor / admin**: returns all sessions, optionally filtered by `status`.
    """
    patient_client = PatientServiceClient()
    async with AsyncSessionLocal() as db:
        svc = TriageSessionService(TriageSessionRepository(db))
        sessions = await svc.list_sessions(
            requester_id  = x_user_id,
            role          = x_user_role,
            status_filter = status,
        )
        await db.commit()

    # Fetch patient names in parallel for all sessions
    import asyncio
    async def get_name(session):
        name = await patient_client.get_patient_name(session.patient_id)
        return (session, name)

    results = await asyncio.gather(*[get_name(s) for s in sessions])
    items = [_to_response(s, name) for s, name in results]
    return TriageSessionListResponse(sessions=items, total=len(items))


# ── Get single session ───────────────────────────────────────────────────────

@router.get("/{session_id}", response_model=TriageSessionResponse)
async def get_triage_session(
    session_id:  str,
    x_user_id:   str = Header(...),
    x_user_role: str = Header(...),
):
    """Fetch a single triage session. Patients can only access their own sessions."""
    patient_client = PatientServiceClient()
    try:
        async with AsyncSessionLocal() as db:
            svc     = TriageSessionService(TriageSessionRepository(db))
            session = await svc.get_session(session_id, x_user_id, x_user_role)
            await db.commit()
        patient_name = await patient_client.get_patient_name(session.patient_id)
        return _to_response(session, patient_name)
    except TriageSessionNotFound:
        raise HTTPException(status_code=404, detail="Triage session not found")
    except TriageSessionAccessDenied:
        raise HTTPException(status_code=403, detail="Access denied")


# ── Doctor: confirm ──────────────────────────────────────────────────────────

@router.post("/{session_id}/confirm", response_model=TriageSessionResponse)
async def confirm_triage_session(
    session_id: str,
    body:       DoctorConfirmInput,
    x_user_id:  str = Header(...),
    x_user_role: str = Header(...),
):
    """
    Doctor confirms the AI's specialty suggestion.
    Status → **doctor_confirmed**; final_department = suggested_department.

    If the triage session has a ``pending_booking`` (patient picked a slot but
    the actual appointment was deferred until doctor review), this endpoint
    also creates the real appointment in the Appointment Service.
    """
    if x_user_role not in ("doctor", "admin"):
        raise HTTPException(status_code=403, detail="Only doctors can confirm triage sessions")

    patient_client = PatientServiceClient()
    appointment_client = AppointmentServiceClient()

    try:
        async with AsyncSessionLocal() as db:
            repo    = TriageSessionRepository(db)
            svc     = TriageSessionService(repo)

            # Load session first so we can check pending_booking before confirming
            from Application.triage_session import TriageSessionNotFound as _NotFound
            raw_session = await repo.get_by_id(session_id)
            if not raw_session:
                raise HTTPException(status_code=404, detail="Triage session not found")

            pending = getattr(raw_session, "pending_booking", None)

            session = await svc.doctor_confirm(session_id, x_user_id, body.notes)

            # If the patient had a pending booking request, create the appointment now
            if pending:
                try:
                    result = await appointment_client.create_appointment(
                        doctor_id=pending["doctor_id"],
                        specialty_id=pending["specialty_id"],
                        appointment_date=pending["date"],
                        start_time=pending["time"],
                        patient_id=pending.get("patient_id") or raw_session.patient_id,
                        triage_session_id=session_id,
                        urgency_level=pending.get("urgency_level", "Routine"),
                        referred_by_doctor_id=x_user_id,
                        chief_complaint=None,
                    )
                    appt_id = result.get("id") or result.get("appointment_id")
                    if appt_id:
                        # Persist appointment_id + clear pending_booking on the session
                        raw_session.appointment_id = str(appt_id)
                        raw_session.pending_booking = None
                        await repo.save(raw_session)
                        session.appointment_id = str(appt_id)
                except Exception as e:
                    logger.warning(
                        "confirm_triage_session: failed to create appointment for session %s: %s",
                        session_id, e,
                    )

            await db.commit()

        patient_name = await patient_client.get_patient_name(session.patient_id)
        return _to_response(session, patient_name)
    except TriageSessionNotFound:
        raise HTTPException(status_code=404, detail="Triage session not found")


# ── Doctor: refer to General Medicine ────────────────────────────────────────

@router.post("/{session_id}/refer-internal", response_model=TriageSessionResponse)
async def refer_internal(
    session_id:  str,
    body:        DoctorReferInput,
    x_user_id:   str = Header(...),
    x_user_role: str = Header(...),
):
    """
    Doctor is unsure and redirects patient to General Medicine.
    Status → **referred_internal**; final_department = internal_medicine.
    """
    if x_user_role not in ("doctor", "admin"):
        raise HTTPException(status_code=403, detail="Only doctors can refer triage sessions")

    patient_client = PatientServiceClient()
    try:
        async with AsyncSessionLocal() as db:
            svc     = TriageSessionService(TriageSessionRepository(db))
            session = await svc.doctor_refer_internal(session_id, x_user_id, body.notes)
            await db.commit()
        patient_name = await patient_client.get_patient_name(session.patient_id)
        return _to_response(session, patient_name)
    except TriageSessionNotFound:
        raise HTTPException(status_code=404, detail="Triage session not found")


# ── Doctor: clinical summary ─────────────────────────────────────────────────

@router.get("/{session_id}/summary", response_model=TriageSummaryResponse)
async def get_triage_summary(
    session_id:  str,
    x_user_id:   str = Header(...),
    x_user_role: str = Header(...),
):
    """
    Generate an AI clinical summary of a triage session for doctor review.
    Intended to replace reading the raw conversation — concise, clinically framed,
    and no verbatim patient quotes.

    **Doctor / admin only.** Patients cannot access summaries of other patients' sessions.
    """
    if x_user_role not in ("doctor", "admin"):
        raise HTTPException(status_code=403, detail="Only doctors and admins can view triage summaries")

    try:
        async with AsyncSessionLocal() as db:
            svc = TriageSessionService(TriageSessionRepository(db))
            llm = WokuClient()
            # Fetch session first so we can reuse its status after summary generation
            session = await svc._repo.get_by_id(session_id)
            if not session:
                raise TriageSessionNotFound(session_id)
            summary = await svc.generate_summary(
                session_id=session_id,
                requester_id=x_user_id,
                role=x_user_role,
                llm_client=llm,
            )
            await db.commit()

        return TriageSummaryResponse(
            **summary,
            session_id=session_id,
            triage_status=(
                session.status.value if session and hasattr(session.status, "value")
                else (str(session.status) if session else None)
            ),
        )
    except TriageSessionNotFound:
        raise HTTPException(status_code=404, detail="Triage session not found")
    except TriageSessionAccessDenied:
        raise HTTPException(status_code=403, detail="Access denied")
    except Exception as exc:
        logger.error("Error generating triage summary for %s: %s", session_id, exc)
        raise HTTPException(status_code=500, detail="Failed to generate summary")


# ── Booking: check availability ─────────────────────────────────────────────

class BookingAvailabilityRequest(BaseModel):
    preferred_date: str  # ISO date string e.g. "2025-04-20"


class AvailableSlotResponse(BaseModel):
    doctor_id: str
    doctor_name: str
    specialty_id: str
    start_time: str
    end_time: str


class BookingAvailabilityResponse(BaseModel):
    session_id: str
    department: str
    preferred_date: str
    slots: list[AvailableSlotResponse]


@router.post(
    "/{session_id}/availability",
    response_model=BookingAvailabilityResponse,
    tags=["AI - Triage Booking"],
)
async def check_booking_availability(
    session_id:  str,
    body:        BookingAvailabilityRequest,
    x_user_id:   str = Header(...),
    x_user_role: str = Header(...),
):
    """
    Check available slots for the suggested department on the given date.
    Used by the AI after [R] recommendation to present booking options.

    Returns a flat list of available slots with doctor info.
    """
    # Normalize role to lowercase for consistent session access control
    normalized_role = (x_user_role or "").strip().lower()
    
    try:
        async with AsyncSessionLocal() as db:
            svc = TriageSessionService(TriageSessionRepository(db))
            session = await svc.load_session(session_id, x_user_id, normalized_role)
            await db.commit()
    except TriageSessionNotFound:
        raise HTTPException(status_code=404, detail="Triage session not found")
    except TriageSessionAccessDenied:
        raise HTTPException(status_code=403, detail="Access denied")

    booking_svc = BookingUseCase(
        llm=WokuClient(),
        appointment_client=AppointmentServiceClient(),
        triage_repo=TriageSessionRepository(db),
    )

    department = session.final_department or session.suggested_department
    slots = await booking_svc.check_availability_and_suggest(session, body.preferred_date)

    return BookingAvailabilityResponse(
        session_id=session_id,
        department=department or "",
        preferred_date=body.preferred_date,
        slots=[
            AvailableSlotResponse(
                doctor_id=s["doctor_id"],
                doctor_name=s["doctor_name"],
                specialty_id=s["specialty_id"],
                start_time=s["start_time"],
                end_time=s["end_time"],
            )
            for s in slots
        ],
    )


# ── Booking: create appointment ──────────────────────────────────────────────

class CreateBookingRequest(BaseModel):
    doctor_id: str
    specialty_id: str
    appointment_date: str  # ISO date
    start_time: str        # HH:MM


@router.post("/{session_id}/book", tags=["AI - Triage Booking"])
async def create_booking(
    session_id:  str,
    body:        CreateBookingRequest,
    x_user_id:   str = Header(...),
    x_user_role: str = Header(...),
):
    """
    Create an appointment for the given triage session.
    The appointment is tagged with ai_referred=True so the doctor
    must confirm manually (auto_confirm is overridden).

    Returns the created appointment data.
    """
    # Normalize role to lowercase for consistent session access control
    normalized_role = (x_user_role or "").strip().lower()
    
    try:
        async with AsyncSessionLocal() as db:
            svc = TriageSessionService(TriageSessionRepository(db))
            session = await svc.load_session(session_id, x_user_id, normalized_role)
            await db.commit()
    except TriageSessionNotFound:
        raise HTTPException(status_code=404, detail="Triage session not found")
    except TriageSessionAccessDenied:
        raise HTTPException(status_code=403, detail="Access denied")

    booking_svc = BookingUseCase(
        llm=WokuClient(),
        appointment_client=AppointmentServiceClient(),
        triage_repo=TriageSessionRepository(db),
    )

    result = await booking_svc.create_appointment(
        session=session,
        doctor_id=body.doctor_id,
        specialty_id=body.specialty_id,
        appointment_date=body.appointment_date,
        start_time=body.start_time,
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    # Track appointment_id back on the triage session
    appt_id = result.get("id")
    if appt_id:
        session.appointment_id = str(appt_id)
        await TriageSessionRepository(db).save(session)
        await db.commit()

    return result
