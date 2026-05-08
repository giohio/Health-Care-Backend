from fastapi import APIRouter, Header, Depends, HTTPException
from fastapi.responses import StreamingResponse
from presentation.schema import ClinicalAssistInput
from Application.clinical_assist import ClinicalAssistUseCase
from Application.chat_session import ChatSessionNotFound, ChatSessionAccessDenied, ChatSessionService
from presentation.dependencies import get_clinical_assist_usecase
from infrastructure.database.session import AsyncSessionLocal
from infrastructure.repositories.chat_session_repository import ChatSessionRepository
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/clinical-assist", tags=["AI - Clinical Decision Support"])

_DOCTOR_ROLES = {"doctor", "admin"}


@router.post("")
async def clinical_assist(
    body:        ClinicalAssistInput,
    x_user_id:   str = Header(...),
    x_user_role: str = Header(...),
    use_case:    ClinicalAssistUseCase = Depends(get_clinical_assist_usecase),
):
    """
    Doctor-facing clinical decision support with persistent session history — streaming SSE.

    Provides evidence-based differential diagnoses, treatment options, and
    guideline-referenced management plans. Restricted to doctor / admin roles.

    On the first call, omit ``session_id`` — the server creates a new session and
    emits ``event: session_id`` as the first SSE event. Include it in subsequent
    requests to maintain conversation history.

    SSE events:
    - ``event: session_id  data: <uuid>``   — emitted first (new sessions only)
    - ``data: <text chunk>``                — streamed AI response
    - ``data: [DONE]``                      — stream complete
    """
    normalized_role = (x_user_role or "").strip().lower()
    if normalized_role not in _DOCTOR_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Clinical decision support is restricted to doctors and admins.",
        )

    # Load or create session
    async with AsyncSessionLocal() as db:
        svc = ChatSessionService(ChatSessionRepository(db))
        try:
            if body.session_id:
                session = await svc.load_session(
                    body.session_id, x_user_id, normalized_role
                )
                is_new = False
            else:
                session = await svc.start_session(
                    user_id      = x_user_id,
                    user_role    = normalized_role,
                    session_type = "clinical_assist",
                    patient_id   = body.patient_id,
                    department   = body.department,
                )
                is_new = True
            await db.commit()
        except ChatSessionNotFound:
            raise HTTPException(status_code=404, detail="Chat session not found")
        except ChatSessionAccessDenied:
            raise HTTPException(status_code=403, detail="Access denied to this session")

    session_id   = session.id
    history_snap = list(session.messages)

    async def event_stream():
        if is_new:
            yield f"event: session_id\ndata: {session_id}\n\n"

        collected: list[str] = []
        async for chunk in use_case.execute(
            question     = body.question,
            x_user_id    = x_user_id,
            x_user_role  = normalized_role,
            patient_id   = body.patient_id,
            department   = body.department,
            history      = history_snap if history_snap else None,
        ):
            collected.append(chunk)
            safe = chunk.replace("\n", "\ndata: ")
            yield f"data: {safe}\n\n"

        yield "data: [DONE]\n\n"

        # Persist turn after streaming completes
        full_response = "".join(collected)
        try:
            async with AsyncSessionLocal() as db2:
                svc2 = ChatSessionService(ChatSessionRepository(db2))
                session2 = await svc2._repo.get_by_id(session_id)
                if session2:
                    await svc2.finish_turn(session2, body.question, full_response)
                await db2.commit()
        except Exception:
            logger.exception(
                "Failed to persist clinical_assist turn for session %s", session_id
            )

    return StreamingResponse(event_stream(), media_type="text/event-stream")

