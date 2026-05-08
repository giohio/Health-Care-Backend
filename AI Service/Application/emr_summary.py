from typing import AsyncGenerator, Optional
from Domain.entities import EmrSummaryRequest
from Domain.prompts import EMR_SUMMARY_SYSTEM, build_emr_summary_prompt
from Domain.interfaces import ILLMClient, IClinicalClient, IEmrResultClient, IRetriever


class EmrSummaryUseCase:
    """
    Tier 2 on-demand: Doctor opens EMR → stream patient summary.
    Sync streaming — doctor waits in EMR dashboard.
    """

    def __init__(self, llm: ILLMClient, clinical: IClinicalClient,
                 emr_result: IEmrResultClient,
                 retriever: Optional[IRetriever] = None):
        self._llm        = llm
        self._clinical   = clinical
        self._emr_result = emr_result
        self._retriever  = retriever

    async def execute(
        self,
        request:     EmrSummaryRequest,
        token:       str,
        x_user_id:   str,
        x_user_role: str,
    ) -> AsyncGenerator[str, None]:

        context = await self._clinical.get_patient_context(
            request.patient_id, x_user_id, x_user_role
        )

        recent_labs = await self._emr_result.get_recent_results(
            request.patient_id, token, x_user_id, x_user_role, limit=5
        )

        rag_context = ""
        if self._retriever:
            diag_query = " ".join(context.active_diagnoses[:3]) or "general medicine"
            rag_context = await self._retriever.get_context(
                diag_query, department=None, top_k=3
            )

        user_prompt = build_emr_summary_prompt(
            context, recent_labs, user_language=request.language, rag_context=rag_context
        )

        async for chunk in self._llm.stream_completion(
            system_prompt=EMR_SUMMARY_SYSTEM,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=2048,
        ):
            yield chunk

