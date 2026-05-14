"""
Extra unit tests for AI Service to push total coverage above 85%.

Targets:
  - Application/lab_suggestion.py     (was 38%)
  - Application/auscultation_analysis.py (was 68%)
  - infrastructure/llm/groq_client.py (was 66%)
  - infrastructure/repositories/triage_session_repository.py (was 37%)
  - infrastructure/repositories/chat_session_repository.py   (was 44%)
"""
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from typing import AsyncGenerator

import pytest


# ===========================================================================
# Helpers / shared fakes
# ===========================================================================

def _make_fake_llm(response: str = "OK response") -> MagicMock:
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=response)
    return llm


def _make_fake_clinical(ctx=None) -> MagicMock:
    clinical = MagicMock()
    if ctx is None:
        ctx = {}
    # Return a PatientContext dataclass so that context.full_name etc. work
    # (prompts.py accesses context as an object, not as a dict).
    from Domain.entities import PatientContext
    clinical.get_patient_context = AsyncMock(return_value=PatientContext(
        patient_id="p-abc",
        full_name=ctx.get("name", "N/A"),
        age=ctx.get("age"),
        gender=ctx.get("gender"),
        active_diagnoses=ctx.get("active_diagnoses", []),
        current_medications=ctx.get("current_medications", []),
        allergies=ctx.get("allergies", ""),
        chronic_conditions=ctx.get("chronic_conditions", ""),
    ))
    return clinical


# ===========================================================================
# LabSuggestionUseCase
# ===========================================================================

class TestLabSuggestionUseCase:
    """Covers Application/lab_suggestion.py (was 38%)."""

    @pytest.mark.asyncio
    async def test_execute_returns_suggestions_without_patient(self):
        from Application.lab_suggestion import LabSuggestionUseCase

        llm = _make_fake_llm(json.dumps({"suggestions": ["CBC", "LFT"]}))
        clinical = _make_fake_clinical()
        uc = LabSuggestionUseCase(llm, clinical)

        result = await uc.execute(
            symptoms="fever and fatigue",
            x_user_id="doc-1",
            x_user_role="doctor",
        )
        assert result["suggestions"] == ["CBC", "LFT"]
        clinical.get_patient_context.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_fetches_context_when_patient_id_given(self):
        from Application.lab_suggestion import LabSuggestionUseCase

        llm = _make_fake_llm(json.dumps({"suggestions": ["Chest X-Ray"]}))
        clinical = _make_fake_clinical({"name": "Nguyen Van A"})
        uc = LabSuggestionUseCase(llm, clinical)

        result = await uc.execute(
            symptoms="cough",
            x_user_id="doc-1",
            x_user_role="doctor",
            patient_id="p-abc",
            department="respiratory",
        )
        assert "suggestions" in result
        clinical.get_patient_context.assert_called_once_with("p-abc", "doc-1", "doctor")

    @pytest.mark.asyncio
    async def test_execute_falls_back_on_invalid_json(self):
        from Application.lab_suggestion import LabSuggestionUseCase

        llm = _make_fake_llm("this is not json at all")
        clinical = _make_fake_clinical()
        uc = LabSuggestionUseCase(llm, clinical)

        result = await uc.execute(symptoms="headache", x_user_id="u", x_user_role="doctor")
        assert result == {"suggestions": []}

    @pytest.mark.asyncio
    async def test_execute_falls_back_when_suggestions_key_missing(self):
        from Application.lab_suggestion import LabSuggestionUseCase

        llm = _make_fake_llm(json.dumps({"tests": ["CBC"]}))  # wrong key
        clinical = _make_fake_clinical()
        uc = LabSuggestionUseCase(llm, clinical)

        result = await uc.execute(symptoms="headache", x_user_id="u", x_user_role="doctor")
        assert result == {"suggestions": []}


# ===========================================================================
# AuscultationAnalysisUseCase
# ===========================================================================

class TestAuscultationAnalysisUseCase:
    """Covers Application/auscultation_analysis.py (was 68%)."""

    def _make_uc(self, gemini_findings=None, llm_response="draft text", retriever=None):
        from Application.auscultation_analysis import AuscultationAnalysisUseCase

        llm = _make_fake_llm(llm_response)
        gemini = MagicMock()
        gemini.extract_findings = AsyncMock(return_value=gemini_findings or {
            "keywords": ["wheezing", "crackles"],
            "confidence": 0.85,
            "impression": "Bilateral crackles",
        })
        clinical = _make_fake_clinical({"name": "Patient A", "age": 45})

        if retriever is None:
            retriever = MagicMock()
            retriever.get_context = AsyncMock(return_value="")

        return AuscultationAnalysisUseCase(llm, gemini, clinical, retriever)

    @pytest.mark.asyncio
    async def test_execute_success_with_spectrogram(self):
        """Happy path: librosa available, gemini finds findings, groq synthesizes."""
        from Application.auscultation_analysis import AuscultationAnalysisUseCase

        uc = self._make_uc()

        with patch("Application.auscultation_analysis._audio_to_spectrogram_png",
                   return_value=b"fake_png_bytes"):
            result = await uc.execute(
                audio_bytes=b"audio data",
                patient_id="p-1",
                sound_type="lung_sounds",
                department="respiratory",
                language="vi",
                x_user_id="doc-1",
                x_user_role="doctor",
            )

        assert result.draft_text == "draft text"
        assert result.confidence == pytest.approx(0.85)
        assert result.result_id == "auscultation"

    @pytest.mark.asyncio
    async def test_execute_fallback_when_spectrogram_fails(self):
        """When librosa raises RuntimeError, findings dict has 'error' key → early return."""
        uc = self._make_uc()

        with patch("Application.auscultation_analysis._audio_to_spectrogram_png",
                   side_effect=RuntimeError("librosa not installed")):
            result = await uc.execute(
                audio_bytes=b"audio",
                patient_id="p-1",
                sound_type="lung_sounds",
                department="respiratory",
                language="vi",
                x_user_id="doc-1",
                x_user_role="doctor",
            )

        # The early-return path sets draft_text to the handcoded warning
        assert "Unable to analyze audio" in result.draft_text
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_execute_with_rag_retriever_appends_context(self):
        """When retriever returns context, it is prepended to the user prompt."""
        from Application.auscultation_analysis import AuscultationAnalysisUseCase

        retriever = MagicMock()
        retriever.get_context = AsyncMock(return_value="RAG guideline text")
        uc = self._make_uc(retriever=retriever)

        with patch("Application.auscultation_analysis._audio_to_spectrogram_png",
                   return_value=b"png"):
            result = await uc.execute(
                audio_bytes=b"audio",
                patient_id="p-1",
                sound_type="heart_sounds",
                department="cardiology",
                language="en",
                x_user_id="doc-1",
                x_user_role="doctor",
            )

        retriever.get_context.assert_called_once()
        assert result.draft_text == "draft text"

    @pytest.mark.asyncio
    async def test_execute_no_retriever(self):
        """When retriever is None, rag_context is skipped."""
        from Application.auscultation_analysis import AuscultationAnalysisUseCase

        uc = self._make_uc(retriever=None)

        with patch("Application.auscultation_analysis._audio_to_spectrogram_png",
                   return_value=b"png"):
            result = await uc.execute(
                audio_bytes=b"audio",
                patient_id="p-1",
                sound_type="lung_sounds",
                department="respiratory",
                language="vi",
                x_user_id="doc-1",
                x_user_role="doctor",
            )

        assert result.result_id == "auscultation"


# ===========================================================================
# GroqClient
# ===========================================================================

class TestGroqClientExtra:
    """Extra tests for infrastructure/llm/groq_client.py (was 66%)."""

    def _make_client(self):
        from infrastructure.llm.groq_client import GroqClient
        with patch("infrastructure.llm.groq_client.AsyncGroq"), \
             patch("infrastructure.llm.groq_client.get_settings") as mock_settings:
            mock_settings.return_value.GROQ_API_KEY = "key"
            mock_settings.return_value.GROQ_TEXT_MODEL = "llama3-8b"
            mock_settings.return_value.LLM_TIMEOUT_S = 30
            client = GroqClient()
        return client

    @pytest.mark.asyncio
    async def test_complete_json_mode_returns_raw_text(self):
        from infrastructure.llm.groq_client import GroqClient
        with patch("infrastructure.llm.groq_client.AsyncGroq") as mock_groq, \
             patch("infrastructure.llm.groq_client.get_settings") as mock_settings:
            mock_settings.return_value.GROQ_API_KEY = "key"
            mock_settings.return_value.GROQ_TEXT_MODEL = "llama3"
            mock_settings.return_value.LLM_TIMEOUT_S = 30

            mock_resp = MagicMock()
            mock_resp.choices[0].message.content = '{"result": "ok"}'
            mock_groq.return_value.chat.completions.create = AsyncMock(return_value=mock_resp)

            client = GroqClient()
            result = await client.complete(
                system_prompt="system",
                user_prompt="user",
                json_mode=True,
            )
            assert result == '{"result": "ok"}'

    @pytest.mark.asyncio
    async def test_complete_non_json_mode_appends_disclaimer(self):
        from infrastructure.llm.groq_client import GroqClient
        with patch("infrastructure.llm.groq_client.AsyncGroq") as mock_groq, \
             patch("infrastructure.llm.groq_client.get_settings") as mock_settings:
            mock_settings.return_value.GROQ_API_KEY = "key"
            mock_settings.return_value.GROQ_TEXT_MODEL = "llama3"
            mock_settings.return_value.LLM_TIMEOUT_S = 30

            mock_resp = MagicMock()
            mock_resp.choices[0].message.content = "Analysis result"
            mock_groq.return_value.chat.completions.create = AsyncMock(return_value=mock_resp)

            client = GroqClient()
            result = await client.complete(
                system_prompt="system",
                user_prompt="some english text",
                json_mode=False,
            )
            assert "Analysis result" in result
            # Disclaimer appended
            assert len(result) > len("Analysis result")

    @pytest.mark.asyncio
    async def test_complete_raises_runtime_error_on_exception(self):
        from infrastructure.llm.groq_client import GroqClient
        with patch("infrastructure.llm.groq_client.AsyncGroq") as mock_groq, \
             patch("infrastructure.llm.groq_client.get_settings") as mock_settings:
            mock_settings.return_value.GROQ_API_KEY = "key"
            mock_settings.return_value.GROQ_TEXT_MODEL = "llama3"
            mock_settings.return_value.LLM_TIMEOUT_S = 30

            mock_groq.return_value.chat.completions.create = AsyncMock(
                side_effect=Exception("API down")
            )
            client = GroqClient()
            with pytest.raises(RuntimeError, match="Groq API error"):
                await client.complete(system_prompt="s", user_prompt="u")

    @pytest.mark.asyncio
    async def test_complete_structured_returns_dict(self):
        from infrastructure.llm.groq_client import GroqClient
        schema = {"type": "object", "properties": {"value": {"type": "string"}}}
        with patch("infrastructure.llm.groq_client.AsyncGroq") as mock_groq, \
             patch("infrastructure.llm.groq_client.get_settings") as mock_settings:
            mock_settings.return_value.GROQ_API_KEY = "key"
            mock_settings.return_value.GROQ_TEXT_MODEL = "llama3"
            mock_settings.return_value.LLM_TIMEOUT_S = 30

            mock_resp = MagicMock()
            mock_resp.choices[0].message.content = '{"value": "test"}'
            mock_groq.return_value.chat.completions.create = AsyncMock(return_value=mock_resp)

            client = GroqClient()
            result = await client.complete_structured(
                system_prompt="s",
                user_prompt="u",
                response_schema=schema,
            )
            assert result == {"value": "test"}

    @pytest.mark.asyncio
    async def test_complete_structured_returns_empty_dict_on_error(self):
        from infrastructure.llm.groq_client import GroqClient
        with patch("infrastructure.llm.groq_client.AsyncGroq") as mock_groq, \
             patch("infrastructure.llm.groq_client.get_settings") as mock_settings:
            mock_settings.return_value.GROQ_API_KEY = "key"
            mock_settings.return_value.GROQ_TEXT_MODEL = "llama3"
            mock_settings.return_value.LLM_TIMEOUT_S = 30

            mock_groq.return_value.chat.completions.create = AsyncMock(
                side_effect=Exception("API error")
            )
            client = GroqClient()
            result = await client.complete_structured(
                system_prompt="s",
                user_prompt="u",
                response_schema={},
            )
            assert result == {}

    @pytest.mark.asyncio
    async def test_stream_conversation_yields_chunks(self):
        from infrastructure.llm.groq_client import GroqClient

        async def _fake_stream(*args, **kwargs):
            for text in ["Hello", " World"]:
                chunk = MagicMock()
                chunk.choices[0].delta.content = text
                yield chunk

        with patch("infrastructure.llm.groq_client.AsyncGroq") as mock_groq, \
             patch("infrastructure.llm.groq_client.get_settings") as mock_settings:
            mock_settings.return_value.GROQ_API_KEY = "key"
            mock_settings.return_value.GROQ_TEXT_MODEL = "llama3"
            mock_settings.return_value.LLM_TIMEOUT_S = 30

            mock_groq.return_value.chat.completions.create = AsyncMock(
                return_value=_fake_stream()
            )
            client = GroqClient()
            chunks = []
            async for chunk in client.stream_conversation(
                messages=[{"role": "user", "content": "Hi"}]
            ):
                chunks.append(chunk)
            assert chunks == ["Hello", " World"]

    @pytest.mark.asyncio
    async def test_stream_conversation_error_yields_vi_message(self):
        from infrastructure.llm.groq_client import GroqClient

        with patch("infrastructure.llm.groq_client.AsyncGroq") as mock_groq, \
             patch("infrastructure.llm.groq_client.get_settings") as mock_settings:
            mock_settings.return_value.GROQ_API_KEY = "key"
            mock_settings.return_value.GROQ_TEXT_MODEL = "llama3"
            mock_settings.return_value.LLM_TIMEOUT_S = 30

            mock_groq.return_value.chat.completions.create = AsyncMock(
                side_effect=Exception("fail")
            )
            client = GroqClient()
            chunks = []
            async for chunk in client.stream_conversation(
                messages=[{"role": "user", "content": "Xin chào"}]
            ):
                chunks.append(chunk)
            # Should yield the Vietnamese error message
            assert any("Xin lỗi" in c or "[R]" in c for c in chunks)


# ===========================================================================
# TriageSessionRepository (unit — mocked SQLAlchemy session)
# ===========================================================================

class TestTriageSessionRepository:
    """Covers infrastructure/repositories/triage_session_repository.py (was 37%)."""

    def _make_session(self):
        session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)
        session.flush = AsyncMock()
        session.add = MagicMock()
        return session

    def _make_entity(self, **kwargs):
        from Domain.entities import TriageSession
        defaults = dict(
            id=str(uuid.uuid4()),
            patient_id="p-1",
            status="active",
            messages=[],
            suggested_department=None,
            urgency_level=None,
            doctor_id=None,
            final_department=None,
            doctor_notes=None,
            created_at=None,
            updated_at=None,
            completed_at=None,
        )
        defaults.update(kwargs)
        return TriageSession(**defaults)

    def _make_model(self, entity):
        from infrastructure.database.models import TriageSessionModel
        model = MagicMock(spec=TriageSessionModel)
        model.id = uuid.UUID(entity.id)
        model.patient_id = entity.patient_id
        model.status = entity.status
        model.messages = entity.messages
        model.suggested_department = entity.suggested_department
        model.urgency_level = entity.urgency_level
        model.doctor_id = entity.doctor_id
        model.final_department = entity.final_department
        model.doctor_notes = entity.doctor_notes
        model.created_at = None
        model.updated_at = None
        model.completed_at = entity.completed_at
        return model

    @pytest.mark.asyncio
    async def test_save_new_entity_calls_add(self):
        from infrastructure.repositories.triage_session_repository import TriageSessionRepository
        session = self._make_session()
        entity = self._make_entity()

        # No existing model
        session.execute.return_value.scalar_one_or_none.return_value = None

        repo = TriageSessionRepository(session)
        result = await repo.save(entity)

        session.add.assert_called_once()
        session.flush.assert_called_once()
        assert result.id == entity.id

    @pytest.mark.asyncio
    async def test_save_existing_entity_updates_fields(self):
        from infrastructure.repositories.triage_session_repository import TriageSessionRepository
        session = self._make_session()
        entity = self._make_entity(status="completed")
        model = self._make_model(entity)

        session.execute.return_value.scalar_one_or_none.return_value = model

        repo = TriageSessionRepository(session)
        result = await repo.save(entity)

        assert model.status == "completed"
        session.add.assert_not_called()
        session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_id_returns_entity_when_found(self):
        from infrastructure.repositories.triage_session_repository import TriageSessionRepository
        session = self._make_session()
        entity = self._make_entity()
        model = self._make_model(entity)

        session.execute.return_value.scalar_one_or_none.return_value = model

        repo = TriageSessionRepository(session)
        result = await repo.get_by_id(entity.id)

        assert result is not None
        assert result.id == entity.id

    @pytest.mark.asyncio
    async def test_get_by_id_returns_none_when_not_found(self):
        from infrastructure.repositories.triage_session_repository import TriageSessionRepository
        session = self._make_session()
        session.execute.return_value.scalar_one_or_none.return_value = None

        repo = TriageSessionRepository(session)
        result = await repo.get_by_id(str(uuid.uuid4()))
        assert result is None

    @pytest.mark.asyncio
    async def test_list_by_patient_returns_entities(self):
        from infrastructure.repositories.triage_session_repository import TriageSessionRepository
        session = self._make_session()
        entity = self._make_entity()
        model = self._make_model(entity)

        session.execute.return_value.scalars.return_value.all.return_value = [model]

        repo = TriageSessionRepository(session)
        results = await repo.list_by_patient(entity.patient_id)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_list_all_no_filter(self):
        from infrastructure.repositories.triage_session_repository import TriageSessionRepository
        session = self._make_session()
        entity = self._make_entity()
        model = self._make_model(entity)

        session.execute.return_value.scalars.return_value.all.return_value = [model]

        repo = TriageSessionRepository(session)
        results = await repo.list_all()
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_list_all_with_status_filter(self):
        from infrastructure.repositories.triage_session_repository import TriageSessionRepository
        session = self._make_session()
        session.execute.return_value.scalars.return_value.all.return_value = []

        repo = TriageSessionRepository(session)
        results = await repo.list_all(status_filter="completed")
        assert results == []


# ===========================================================================
# ChatSessionRepository (unit — mocked SQLAlchemy session)
# ===========================================================================

class TestChatSessionRepository:
    """Covers infrastructure/repositories/chat_session_repository.py (was 44%)."""

    def _make_session(self):
        session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)
        session.flush = AsyncMock()
        session.add = MagicMock()
        return session

    def _make_chat_model(self, session_id: str, user_id: str = "u-1"):
        model = MagicMock()
        model.id = uuid.UUID(session_id)
        model.user_id = user_id
        model.user_role = "doctor"
        model.session_type = "lab_chat"
        model.messages = []
        model.patient_id = None
        model.department = None
        model.created_at = None
        model.updated_at = None
        return model

    @pytest.mark.asyncio
    async def test_get_by_id_returns_none_when_not_found(self):
        from infrastructure.repositories.chat_session_repository import ChatSessionRepository
        session = self._make_session()
        session.execute.return_value.scalar_one_or_none.return_value = None

        repo = ChatSessionRepository(session)
        result = await repo.get_by_id(str(uuid.uuid4()))
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_id_returns_entity_when_found(self):
        from infrastructure.repositories.chat_session_repository import ChatSessionRepository
        session = self._make_session()
        sid = str(uuid.uuid4())
        model = self._make_chat_model(sid)
        session.execute.return_value.scalar_one_or_none.return_value = model

        repo = ChatSessionRepository(session)
        result = await repo.get_by_id(sid)
        assert result is not None
        assert result.id == sid

    @pytest.mark.asyncio
    async def test_save_new_session_calls_add(self):
        from infrastructure.repositories.chat_session_repository import ChatSessionRepository
        from Domain.entities import ChatSession
        session = self._make_session()

        sid = str(uuid.uuid4())
        entity = ChatSession(
            id=sid,
            user_id="u-1",
            user_role="doctor",
            session_type="lab_chat",
            messages=[],
            patient_id=None,
            department=None,
        )

        # Simulate no existing model
        session.execute.return_value.scalar_one_or_none.return_value = None
        # _to_entity needs model.id, etc — return a proper model from flush
        model = self._make_chat_model(sid)
        # After add, session.flush is called, then _to_entity uses `model`
        # Patch _to_entity to avoid MagicMock attribute issues
        with patch.object(
            ChatSessionRepository,
            "_to_entity",
            return_value=entity,
        ):
            repo = ChatSessionRepository(session)
            result = await repo.save(entity)

        session.add.assert_called_once()
        session.flush.assert_called_once()
        assert result.id == sid

    @pytest.mark.asyncio
    async def test_save_existing_session_updates_messages(self):
        from infrastructure.repositories.chat_session_repository import ChatSessionRepository
        from Domain.entities import ChatSession
        session = self._make_session()

        sid = str(uuid.uuid4())
        entity = ChatSession(
            id=sid,
            user_id="u-1",
            user_role="doctor",
            session_type="lab_chat",
            messages=[{"role": "user", "content": "Hello"}],
            patient_id="p-1",
            department="lab",
        )
        model = self._make_chat_model(sid)
        session.execute.return_value.scalar_one_or_none.return_value = model

        with patch.object(
            ChatSessionRepository,
            "_to_entity",
            return_value=entity,
        ):
            repo = ChatSessionRepository(session)
            result = await repo.save(entity)

        # Should update model messages, not add
        session.add.assert_not_called()
        session.flush.assert_called_once()
        assert result.id == sid
