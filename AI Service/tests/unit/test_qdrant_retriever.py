"""
Unit tests for infrastructure/retriever/qdrant_retriever.py

All external I/O (Qdrant, Ollama HTTP) is fully mocked.
No real network calls are made.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers / Fakes
# ---------------------------------------------------------------------------

def _make_qdrant_hit(text: str, department: str, score: float = 0.9,
                     source: str = "https://example.com",
                     section: str = "Treatment") -> dict:
    return {
        "id": "point-1",
        "score": score,
        "payload": {
            "text": text,
            "department": department,
            "source": source,
            "section_heading": section,
        },
    }


# ---------------------------------------------------------------------------
# _embed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_embed_calls_ollama_endpoint():
    """_embed should POST to /api/embed with model and input list, return first embedding."""
    from infrastructure.retriever.qdrant_retriever import QdrantRetriever

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"embeddings": [[0.1] * 768]}

    with patch("infrastructure.retriever.qdrant_retriever.get_settings") as mock_settings, \
         patch("httpx.AsyncClient") as mock_http_cls:

        s = MagicMock()
        s.RAG_ENABLED = True
        s.QDRANT_URL = "http://qdrant:6333"
        s.QDRANT_COLLECTION = "clinical_guidelines"
        s.OLLAMA_URL = "http://ollama:11434"
        mock_settings.return_value = s

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_instance.post = AsyncMock(return_value=mock_resp)
        mock_http_cls.return_value = mock_client_instance

        retriever = QdrantRetriever()
        vec = await retriever._embed("test query")

    assert vec == [0.1] * 768
    mock_client_instance.post.assert_called_once()
    call_args = mock_client_instance.post.call_args
    assert "/api/embed" in call_args[0][0]
    assert call_args[1]["json"]["input"] == ["test query"]
    assert call_args[1]["json"]["model"] == "nomic-embed-text"


# ---------------------------------------------------------------------------
# _search
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_calls_qdrant_rest_api():
    """_search should POST to Qdrant REST /points/search endpoint."""
    from infrastructure.retriever.qdrant_retriever import QdrantRetriever

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "result": [
            _make_qdrant_hit("HbA1c above 6.5% confirms diabetes.", "endocrinology", score=0.95),
            _make_qdrant_hit("Metformin is first-line for type 2 diabetes.", "endocrinology", score=0.88),
        ]
    }

    with patch("infrastructure.retriever.qdrant_retriever.get_settings") as mock_settings, \
         patch("httpx.AsyncClient") as mock_http_cls:

        s = MagicMock()
        s.RAG_ENABLED = True
        s.QDRANT_URL = "http://qdrant:6333"
        s.QDRANT_COLLECTION = "clinical_guidelines"
        s.OLLAMA_URL = "http://ollama:11434"
        mock_settings.return_value = s

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_instance.post = AsyncMock(return_value=mock_resp)
        mock_http_cls.return_value = mock_client_instance

        retriever = QdrantRetriever()
        hits = await retriever._search([0.1] * 768, department=None, top_k=2)

    assert len(hits) == 2
    assert "HbA1c above 6.5%" in hits[0]["text"]
    assert hits[0]["score"] == 0.95

    # Verify REST call
    post_call = mock_client_instance.post.call_args
    assert "/points/search" in post_call[0][0]
    body = post_call[1]["json"]
    assert body["limit"] == 2
    assert body["with_payload"] is True
    assert "filter" not in body


@pytest.mark.asyncio
async def test_search_passes_department_filter():
    """_search must include a department filter when department is provided."""
    from infrastructure.retriever.qdrant_retriever import QdrantRetriever

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"result": []}

    with patch("infrastructure.retriever.qdrant_retriever.get_settings") as mock_settings, \
         patch("httpx.AsyncClient") as mock_http_cls:

        s = MagicMock()
        s.RAG_ENABLED = True
        s.QDRANT_URL = "http://qdrant:6333"
        s.QDRANT_COLLECTION = "clinical_guidelines"
        s.OLLAMA_URL = "http://ollama:11434"
        mock_settings.return_value = s

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_instance.post = AsyncMock(return_value=mock_resp)
        mock_http_cls.return_value = mock_client_instance

        retriever = QdrantRetriever()
        await retriever._search([0.0] * 768, department="cardiology", top_k=3)

    post_call = mock_client_instance.post.call_args
    body = post_call[1]["json"]
    assert "filter" in body
    assert body["filter"]["must"][0]["key"] == "department"
    assert body["filter"]["must"][0]["match"]["value"] == "cardiology"


@pytest.mark.asyncio
async def test_search_with_no_department_no_filter():
    """When department is None, no filter should be sent."""
    from infrastructure.retriever.qdrant_retriever import QdrantRetriever

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"result": []}

    with patch("infrastructure.retriever.qdrant_retriever.get_settings") as mock_settings, \
         patch("httpx.AsyncClient") as mock_http_cls:

        s = MagicMock()
        s.RAG_ENABLED = True
        s.QDRANT_URL = "http://qdrant:6333"
        s.QDRANT_COLLECTION = "clinical_guidelines"
        s.OLLAMA_URL = "http://ollama:11434"
        mock_settings.return_value = s

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_instance.post = AsyncMock(return_value=mock_resp)
        mock_http_cls.return_value = mock_client_instance

        retriever = QdrantRetriever()
        await retriever._search([0.0] * 768, department=None, top_k=3)

    post_call = mock_client_instance.post.call_args
    body = post_call[1]["json"]
    assert "filter" not in body


# ---------------------------------------------------------------------------
# _format
# ---------------------------------------------------------------------------

def test_format_empty_hits_returns_empty_string():
    from infrastructure.retriever.qdrant_retriever import QdrantRetriever
    assert QdrantRetriever._format([]) == ""


def test_format_single_hit_contains_text_and_source():
    from infrastructure.retriever.qdrant_retriever import QdrantRetriever

    hits = [{"text": "Sarcoidosis causes bilateral hilar lymphadenopathy.",
             "source": "https://radiopaedia.org/articles/sarcoidosis",
             "section": "Clinical Features",
             "score": 0.95}]

    result = QdrantRetriever._format(hits)

    assert "Sarcoidosis causes bilateral hilar lymphadenopathy." in result
    assert "radiopaedia.org" in result
    assert "Clinical Features" in result
    assert "KNOWLEDGE BASE CONTEXT" in result
    assert "END CONTEXT" in result


def test_format_multiple_hits_numbered():
    from infrastructure.retriever.qdrant_retriever import QdrantRetriever

    hits = [
        {"text": "First chunk.", "source": "src1", "section": "", "score": 0.9},
        {"text": "Second chunk.", "source": "src2", "section": "", "score": 0.8},
    ]

    result = QdrantRetriever._format(hits)
    assert "[1]" in result
    assert "[2]" in result
    assert "First chunk." in result
    assert "Second chunk." in result


# ---------------------------------------------------------------------------
# get_context — disabled when RAG_ENABLED=False
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_context_returns_empty_when_rag_disabled():
    from infrastructure.retriever.qdrant_retriever import QdrantRetriever

    with patch("infrastructure.retriever.qdrant_retriever.get_settings") as mock_settings:
        s = MagicMock()
        s.RAG_ENABLED = False
        s.QDRANT_URL = "http://qdrant:6333"
        s.QDRANT_COLLECTION = "clinical_guidelines"
        s.OLLAMA_URL = "http://ollama:11434"
        mock_settings.return_value = s

        retriever = QdrantRetriever()
        result = await retriever.get_context("any query")

    assert result == ""


# ---------------------------------------------------------------------------
# get_context — graceful fallback on error
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_context_returns_empty_on_network_error():
    from infrastructure.retriever.qdrant_retriever import QdrantRetriever

    with patch("infrastructure.retriever.qdrant_retriever.get_settings") as mock_settings, \
         patch("httpx.AsyncClient"):

        s = MagicMock()
        s.RAG_ENABLED = True
        s.QDRANT_URL = "http://qdrant:6333"
        s.QDRANT_COLLECTION = "clinical_guidelines"
        s.OLLAMA_URL = "http://ollama:11434"
        mock_settings.return_value = s

        retriever = QdrantRetriever()
        retriever._embed = AsyncMock(side_effect=ConnectionError("Ollama unreachable"))

        result = await retriever.get_context("diabetic retinopathy", department="ophthalmology")

    assert result == ""


# ---------------------------------------------------------------------------
# get_context — happy path end-to-end (all internals mocked)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_context_returns_formatted_context():
    from infrastructure.retriever.qdrant_retriever import QdrantRetriever

    mock_ollama_resp = MagicMock()
    mock_ollama_resp.raise_for_status = MagicMock()
    mock_ollama_resp.json.return_value = {"embeddings": [[0.1] * 768]}

    mock_qdrant_resp = MagicMock()
    mock_qdrant_resp.raise_for_status = MagicMock()
    mock_qdrant_resp.json.return_value = {
        "result": [
            _make_qdrant_hit("HbA1c above 6.5% confirms diabetes.", "endocrinology")
        ]
    }

    with patch("infrastructure.retriever.qdrant_retriever.get_settings") as mock_settings, \
         patch("httpx.AsyncClient") as mock_http_cls:

        s = MagicMock()
        s.RAG_ENABLED = True
        s.QDRANT_URL = "http://qdrant:6333"
        s.QDRANT_COLLECTION = "clinical_guidelines"
        s.OLLAMA_URL = "http://ollama:11434"
        mock_settings.return_value = s

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=[mock_ollama_resp, mock_qdrant_resp])
        mock_http_cls.return_value = mock_client

        retriever = QdrantRetriever()
        result = await retriever.get_context("HbA1c diabetes", department="endocrinology")

    assert "HbA1c above 6.5% confirms diabetes." in result
    assert "KNOWLEDGE BASE CONTEXT" in result
