from typing import AsyncGenerator, Optional
from Domain.prompts import (
    build_lab_chat_messages,
    _build_context_block,
    AI_DISCLAIMER_VI,
    AI_DISCLAIMER_EN,
    _detect_language,
)
from Domain.interfaces import ILLMClient, IClinicalClient, IRetriever


class LabChatUseCase:
    """
    Synchronous streaming Q&A about lab results.

    Works for both patients (plain-language explanation) and doctors
    (clinical interpretation with guideline references).  The system prompt
    is selected based on the caller's X-User-Role header.
    """

    def __init__(
        self,
        llm:       ILLMClient,
        clinical:  IClinicalClient,
        retriever: Optional[IRetriever] = None,
    ) -> None:
        self._llm       = llm
        self._clinical  = clinical
        self._retriever = retriever

    async def execute(
        self,
        question:    str,
        x_user_id:   str,
        x_user_role: str,
        patient_id:  Optional[str] = None,
        department:  Optional[str] = None,
        history:     Optional[list[dict]] = None,
    ) -> AsyncGenerator[str, None]:
        role = "doctor" if x_user_role in ("doctor", "admin") else "patient"

        # Patient context block: only if patient_id provided
        patient_block = ""
        if patient_id:
            ctx = await self._clinical.get_patient_context(
                patient_id, x_user_id, x_user_role
            )
            patient_block = _build_context_block(ctx)

        # RAG: query clinical guidelines using the question
        rag_context = ""
        if self._retriever:
            rag_context = await self._retriever.get_context(
                question, department=department, top_k=3
            )

        messages = build_lab_chat_messages(
            question=question,
            role=role,
            rag_context=rag_context,
            patient_context_block=patient_block,
            history=history,
        )

        async for chunk in self._llm.stream_conversation(
            messages=messages,
            temperature=0.3,
            max_tokens=2048,
        ):
            yield chunk

        # Append disclaimer at the end for patient-facing responses
        if role == "patient":
            lang = _detect_language(question)
            disc = AI_DISCLAIMER_VI if lang == "vi" else AI_DISCLAIMER_EN
            yield f"\n\n{disc}"

