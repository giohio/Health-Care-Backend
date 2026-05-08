import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from infrastructure.clients.appointment_service_client import AppointmentServiceClient


class TestAppointmentServiceClient:
    pass


@pytest.mark.asyncio
async def test_get_upcoming_appointments_success():
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"id": "1", "status": "CONFIRMED"}]
        mock_get.return_value = mock_resp

        client = AppointmentServiceClient("http://test")

        res = await client.get_upcoming_appointments(datetime.now(), datetime.now())
        assert len(res) == 1
        assert res[0]["id"] == "1"

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_instance = MagicMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        mock_instance.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_instance

        client2 = AppointmentServiceClient("http://test")
        client2.client = mock_instance
        res2 = await client2.get_upcoming_appointments(datetime.now(), datetime.now())
        assert len(res2) == 1


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


@pytest.mark.asyncio
async def test_check_overdue_success():
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"processed": 3, "errors": []}

        mock_instance = MagicMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        mock_instance.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_instance

        client = AppointmentServiceClient("http://test")
        result = await client.check_overdue()

        assert result == {"processed": 3, "errors": []}
        mock_instance.post.assert_called_once_with("/internal/overdue-check")


@pytest.mark.asyncio
async def test_check_overdue_failure_returns_zero():
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_instance = MagicMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        mock_instance.post = AsyncMock(side_effect=Exception("unreachable"))
        mock_client_cls.return_value = mock_instance

        client = AppointmentServiceClient("http://test")
        result = await client.check_overdue()

        assert result == {"processed": 0}
