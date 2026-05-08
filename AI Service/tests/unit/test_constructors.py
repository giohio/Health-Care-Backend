"""
Tests for infrastructure constructors and presentation/dependencies.py

These tests cover the __init__ methods of infra clients and LLM wrappers
(which read settings at construction time) as well as the dependency factory
functions used by FastAPI.

No network calls are made — constructors only read settings + store attributes.
"""

import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Infrastructure constructor tests
# ---------------------------------------------------------------------------

def test_groq_client_init_reads_settings():
    """GroqClient.__init__ sets model, timeout from settings."""
    with patch("infrastructure.llm.groq_client.AsyncGroq") as MockAsyncGroq:
        MockAsyncGroq.return_value = MagicMock()
        from infrastructure.llm.groq_client import GroqClient
        client = GroqClient()

    assert client._model is not None
    assert client._timeout > 0


def test_gemini_client_init_reads_settings():
    """GeminiClient.__init__ stores api_key, model, timeout from settings."""
    from infrastructure.llm.gemini_client import GeminiClient
    client = GeminiClient()

    assert client._api_key is not None
    assert client._model == "gemini-3.1-flash-lite"
    assert client._timeout > 0


def test_clinical_client_init_reads_settings():
    """ClinicalClient.__init__ stores base URL and timeout from settings."""
    from infrastructure.clients.clinical_client import ClinicalClient
    client = ClinicalClient()

    assert "http" in client._clinical_base
    assert client._timeout > 0


def test_emr_result_client_init_reads_settings():
    """EmrResultClient.__init__ stores base URL and timeout from settings."""
    from infrastructure.clients.emr_result_client import EmrResultClient
    client = EmrResultClient()

    assert "http" in client._base
    assert client._timeout > 0


# ---------------------------------------------------------------------------
# Dependency factory tests
# ---------------------------------------------------------------------------

def test_get_symptom_usecase_returns_correct_type():
    """Factory function returns SymptomCheckUseCase instance."""
    with patch("infrastructure.llm.groq_client.AsyncGroq"):
        from presentation.dependencies import get_symptom_usecase
        from Application.symptom_check import SymptomCheckUseCase
        use_case = get_symptom_usecase()

    assert isinstance(use_case, SymptomCheckUseCase)


def test_get_emr_summary_usecase_returns_correct_type():
    """Factory function returns EmrSummaryUseCase instance."""
    with patch("infrastructure.llm.groq_client.AsyncGroq"):
        from presentation.dependencies import get_emr_summary_usecase
        from Application.emr_summary import EmrSummaryUseCase
        use_case = get_emr_summary_usecase()

    assert isinstance(use_case, EmrSummaryUseCase)
