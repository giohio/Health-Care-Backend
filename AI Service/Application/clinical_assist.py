from typing import AsyncGenerator, Optional
from Domain.prompts import (
    build_clinical_assist_messages,
    _build_context_block,
)
from Domain.interfaces import ILLMClient, IClinicalClient, IRetriever


class ClinicalAssistUseCase:
    """
    Doctor-facing clinical decision support: differential diagnosis,
    treatment planning, guideline-backed recommendations.

    Access is restricted to doctor / admin roles (enforced in the route layer).
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
        # Fetch patient context if a patient is referenced
        patient_block = ""
        if patient_id:
            ctx = await self._clinical.get_patient_context(
                patient_id, x_user_id, x_user_role
            )
            patient_block = _build_context_block(ctx)

        # RAG: retrieve clinical guidelines relevant to the question
        rag_context = ""
        if self._retriever:
            rag_context = await self._retriever.get_context(
                question, department=department, top_k=4
            )

        messages = build_clinical_assist_messages(
            question=question,
            rag_context=rag_context,
            patient_block=patient_block,
            history=history,
        )

        async for chunk in self._llm.stream_conversation(
            messages=messages,
            temperature=0.3,
            max_tokens=2048,
        ):
            yield chunk

