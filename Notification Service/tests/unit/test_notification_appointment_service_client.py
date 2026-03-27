import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from infrastructure.clients.appointment_service_client import AppointmentServiceClient

@pytest.mark.asyncio
async def test_get_upcoming_appointments_success():
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"id": "1", "status": "CONFIRMED"}]
        mock_get.return_value = mock_resp
        
        client = AppointmentServiceClient("http://test")
        # Overriding the pre-created client in __init__ for easier mocking if needed, 
        # but the patch on httpx.AsyncClient.get should work.
        
        res = await client.get_upcoming_appointments(datetime.now(), datetime.now())
        assert len(res) == 1
        assert res[0]["id"] == "1"

@pytest.mark.asyncio
async def test_get_upcoming_appointments_failure_returns_empty():
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.side_effect = Exception("network error")
        
        client = AppointmentServiceClient("http://test")
        res = await client.get_upcoming_appointments(datetime.now(), datetime.now())
        assert res == []

@pytest.mark.asyncio
async def test_mark_reminder_sent_success():
    with patch("httpx.AsyncClient.put") as mock_put:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_put.return_value = mock_resp
        
        client = AppointmentServiceClient("http://test")
        await client.mark_reminder_sent("app-1", "24h")
        mock_put.assert_called_once()
