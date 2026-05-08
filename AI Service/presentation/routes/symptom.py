from fastapi import APIRouter, Header, Depends, HTTPException
from fastapi.responses import StreamingResponse
from presentation.schema import SymptomCheckInput
from Domain.entities import ConversationTurn, SymptomCheckRequest
from Application.symptom_check import SymptomCheckUseCase
from Application.triage_session import (
    TriageSessionService,
    TriageSessionNotFound,
    TriageSessionAccessDenied,
)
from infrastructure.database.session import AsyncSessionLocal
from infrastructure.repositories.triage_session_repository import TriageSessionRepository
from presentation.dependencies import get_symptom_usecase
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/symptom-check", tags=["AI - Triage"])

# How many leading characters to buffer before emitting the turn-type SSE event.
# [Q] and [R] markers are 3 chars; buffer slightly more to handle multi-byte encoding.
_SIGNAL_BUF_SIZE = 6


def _sse_data(text: str) -> str:
    """Properly encode a text chunk as SSE data field(s).

    SSE spec (RFC 8895): newlines within a data value MUST be sent as
    separate ``data:`` lines, not bare ``\\n`` — otherwise browsers only
    receive the text up to the first bare newline.
    """
    lines = text.split("\n")
    return "\n".join(f"data: {line}" for line in lines) + "\n\n"
_QUESTION_TURN_EVENT = "event: turn_type\ndata: question\n\n"
_RECOMMENDATION_TURN_EVENT = "event: turn_type\ndata: recommendation\n\n"
_SPECIALTIES_MARKER   = SymptomCheckUseCase.SPECIALTIES_MARKER
_APPOINTMENT_MARKER   = SymptomCheckUseCase.APPOINTMENT_MARKER
_QUESTION_TURN_PREFIX = "To recommend the right specialist, "


@router.post("")
async def symptom_check(
    body:        SymptomCheckInput,
    x_user_id:   str = Header(...),
    x_user_role: str = Header(...),
    use_case:    SymptomCheckUseCase = Depends(get_symptom_usecase),
):
    """
    Tier 1 conversational triage — streaming SSE.

    Each call is one patient turn.  Send `session_id` from the previous response
    to continue a conversation.  Omit it to start a new session.

    SSE events emitted per turn:
      event: session_id   →  data: <uuid>                    (always first)
      event: turn_type    →  data: question | recommendation
      event: specialties →  data: ["Cardiology", ...]        (only on recommendation)
      data: <text chunk>  (one per streamed token, [Q]/[R] prefix stripped)
      data: [DONE]
    """
    # Normalize role to lowercase for consistent session access control
    normalized_role = (x_user_role or "").strip().lower()
    
    # ── Step 1: create or load the session (before streaming) ──────────────
    try:
        async with AsyncSessionLocal() as db:
            svc = TriageSessionService(TriageSessionRepository(db))
            if body.session_id:
                logger.info(
                    "Symptom-check load session attempt: session_id=%s user_id=%s role=%s patient_id=%s",
                    body.session_id,
                    x_user_id,
                    normalized_role,
                    body.patient_id,
                )
                session = await svc.load_session(body.session_id, x_user_id, normalized_role)
            else:
                logger.info(
                    "Symptom-check start new session: user_id=%s role=%s patient_id=%s",
                    x_user_id,
                    normalized_role,
                    body.patient_id,
                )
                session = await svc.start_session(body.patient_id)
            await db.commit()
            logger.info(
                "Symptom-check session ready: session_id=%s user_id=%s patient_id=%s",
                session.id,
                x_user_id,
                body.patient_id,
            )
        # Detach the entity from the session before entering the streaming generator.
        # finish_turn will re-attach it using _entity so no redundant get_by_id is needed.
        session_for_persist = session
    except TriageSessionNotFound:
        logger.warning(
            "TriageSessionNotFound in /symptom-check: session_id=%s user_id=%s role=%s patient_id=%s",
            body.session_id,
            x_user_id,
            normalized_role,
            body.patient_id,
        )
        raise HTTPException(status_code=404, detail="Triage session not found")
    except TriageSessionAccessDenied:
        logger.warning(
            "TriageSessionAccessDenied in /symptom-check: session_id=%s user_id=%s role=%s patient_id=%s",
            body.session_id,
            x_user_id,
            normalized_role,
            body.patient_id,
        )
        raise HTTPException(status_code=403, detail="Access denied to this session")

    session_id = session.id

    # Detect language from all user content (prior history + current)
    # Language is inferred from model response in _emit_initial_chunk via _detect_language

    # Convert DB messages → ConversationTurn list for the use case
    history = [
        ConversationTurn(
            role    = "patient" if m["role"] == "user" else "assistant",
            content = m["content"],
        )
        for m in session.messages
    ]

    request = SymptomCheckRequest(
        patient_id           = body.patient_id,
        symptoms             = body.symptoms,
        duration             = body.duration,
        severity             = body.severity,
        conversation_history = history,
        booking_requested    = body.booking_requested,
        session_id           = body.session_id,
        suggested_department = session.suggested_department,
        urgency_level        = session.urgency_level,
    )

    def _emit_initial_chunk(prefix: str, turn_type: str) -> tuple[bool, str, str | None]:
        if turn_type == "question":
            return False, _QUESTION_TURN_EVENT, prefix.lstrip() or None
        return True, _RECOMMENDATION_TURN_EVENT, prefix.lstrip() or None

    # ── Step 2: define event_stream generator ──────────────────────────────
    async def event_stream():
        # Always emit session_id first so the client can store it
        yield f"event: session_id\ndata: {session_id}\n\n"

        # Declared outside try so they're accessible in the finally block even
        # when CancelledError propagates (client disconnect during complete_structured).
        full_chunks:    list[str] = []
        is_recommendation: bool  = False

        try:
            buf:            str      = ""
            signal_emitted: bool     = False

            async for chunk in use_case.execute(request, x_user_id, x_user_role):

                # Intercept APPOINTMENT_MARKER — emitted by confirmation bypass after
                # a successful booking.  FE listens for this event to trigger refetch.
                # Check FIRST so the marker is never appended to full_chunks / persisted.
                if _APPOINTMENT_MARKER in chunk:
                    start = chunk.index(_APPOINTMENT_MARKER) + len(_APPOINTMENT_MARKER)
                    rest  = chunk[start:]
                    end   = rest.index(_APPOINTMENT_MARKER)
                    raw   = rest[:end]
                    try:
                        appt_data = json.loads(raw)
                        yield f"event: appointment_created\ndata: {json.dumps(appt_data)}\n\n"
                    except Exception:
                        pass
                    continue

                full_chunks.append(chunk)

                # Intercept SPECIALTIES_MARKER tokens from the use case.
                # They are yielded after the disclaimer on recommendation turns.
                if _SPECIALTIES_MARKER in chunk:
                    # chunk may be: "...text[SPECIALTIES_MARKER]["Cardiology"][SPECIALTIES_MARKER]"
                    # Extract the JSON array from between the two markers.
                    start = chunk.index(_SPECIALTIES_MARKER) + len(_SPECIALTIES_MARKER)
                    rest   = chunk[start:]
                    end    = rest.index(_SPECIALTIES_MARKER)
                    raw    = rest[:end]
                    specialties = json.loads(raw)

                    # Emit the SSE event
                    yield f"event: specialties\ndata: {json.dumps(specialties)}\n\n"

                    # Emit whatever text comes after the closing marker (unlikely but safe)
                    tail = rest[end + len(_SPECIALTIES_MARKER):]
                    if tail:
                        yield _sse_data(tail)
                    continue

                # Intercept APPOINTMENT_MARKER block removed from here (handled above)

                if not signal_emitted:
                    buf += chunk
                    if len(buf) < _SIGNAL_BUF_SIZE:
                        continue   # accumulate until we can detect the marker

                    signal_emitted = True
                    # Find ALL [Q] and [R] occurrences in the buffer.
                    # The model sometimes emits:  [structured-analysis] [Q] [reasoning] [Q] [text]
                    # We only want the content AFTER the LAST marker.
                    all_q = [i for i in range(len(buf)) if buf[i:i+3] == "[Q]"]
                    all_r = [i for i in range(len(buf)) if buf[i:i+3] == "[R]"]
                    all_markers = sorted(all_q + all_r)
                    if not all_markers:
                        buf = ""
                        continue
                    last_pos = all_markers[-1]
                    # Detect turn type from the LAST marker
                    if last_pos in all_q:
                        turn_type = "question"
                    else:
                        turn_type = "recommendation"
                    prefix = buf[last_pos + 3:].lstrip()
                    if not prefix:
                        # Nothing after marker yet — wait for next chunk
                        signal_emitted = False
                        buf = ""
                        continue
                    is_recommendation, event_payload, _ = _emit_initial_chunk(
                        prefix, turn_type
                    )
                    yield event_payload
                    yield _sse_data(prefix)
                    buf = ""
                    continue

                # Normal chunk — emit directly.
                # Thinking tokens are already filtered at API level (thought: true parts
                # are skipped in GeminiTextClient._stream_one_turn / _extract_text_parts).
                if chunk:
                    yield _sse_data(chunk)

            # Flush buffer if stream ended before _SIGNAL_BUF_SIZE was reached
            if not signal_emitted and buf:
                all_q = [i for i in range(len(buf)) if buf[i:i+3] == "[Q]"]
                all_r = [i for i in range(len(buf)) if buf[i:i+3] == "[R]"]
                all_markers = sorted(all_q + all_r)
                if not all_markers:
                    return
                last_pos = all_markers[-1]
                turn_type = "question" if last_pos in all_q else "recommendation"
                prefix = buf[last_pos + 3:].lstrip()
                if not prefix:
                    return
                is_recommendation, event_payload, _ = _emit_initial_chunk(
                    prefix, turn_type
                )
                yield event_payload
                yield _sse_data(prefix)

        except Exception as e:
            logger.exception("Symptom check stream error: %s", e)
            if not full_chunks:
                # Only show error to user if no AI response was already sent
                yield _RECOMMENDATION_TURN_EVENT
                yield _sse_data("[ERROR] Unable to analyze symptoms. Please try again.")
                full_chunks = ["[ERROR] Unable to analyze symptoms. Please try again."]
                is_recommendation = True

        finally:
            # ── Step 3: persist the completed turn ─────────────────────────
            # Runs on normal exit, exception, AND CancelledError (client disconnect).
            full_response = "".join(full_chunks)
            if full_response:
                try:
                    async with AsyncSessionLocal() as db:
                        svc = TriageSessionService(TriageSessionRepository(db))
                        await svc.finish_turn(
                            session_id         = session_id,
                            patient_message    = body.symptoms,
                            assistant_response = full_response,
                            is_recommendation  = is_recommendation,
                            _entity            = session_for_persist,
                        )
                        await db.commit()
                except Exception:
                    logger.exception("Failed to persist triage turn for session %s", session_id)

        yield _sse_data("[DONE]")

    return StreamingResponse(event_stream(), media_type="text/event-stream")

