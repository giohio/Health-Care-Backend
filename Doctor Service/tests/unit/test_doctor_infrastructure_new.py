import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from infrastructure.clients.appointment_service_client import AppointmentServiceClient
from infrastructure.repositories.appointment_repository import AppointmentRepository

@pytest.mark.asyncio
async def test_appointment_service_client_has_completed_success():
    client = AppointmentServiceClient("http://test")
    patient_id = uuid.uuid4()
    doctor_id = uuid.uuid4()
    
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"has_completed": True}
        mock_get.return_value = mock_resp
        
        result = await client.has_completed_appointment(patient_id, doctor_id)
        assert result is True
        mock_get.assert_called_once()

@pytest.mark.asyncio
async def test_appointment_service_client_get_appointment_not_found():
    client = AppointmentServiceClient("http://test")
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp
        
        result = await client.get_appointment(uuid.uuid4())
        assert result is None

@pytest.mark.asyncio
async def test_doctor_appointment_repository_get_by_id_success():
    mock_client = AsyncMock()
    patient_id = uuid.uuid4()
    doctor_id = uuid.uuid4()
    mock_client.get_appointment.return_value = {
        "patient_id": str(patient_id),
        "doctor_id": str(doctor_id),
        "status": "COMPLETED"
    }
    
    repo = AppointmentRepository(mock_client)
    res = await repo.get_by_id(uuid.uuid4())
    
    assert res.patient_id == patient_id
    assert res.doctor_id == doctor_id
    assert res.status == "COMPLETED"

@pytest.mark.asyncio
async def test_doctor_appointment_repository_get_by_id_none():
    mock_client = AsyncMock()
    mock_client.get_appointment.return_value = None
    repo = AppointmentRepository(mock_client)
    res = await repo.get_by_id(uuid.uuid4())
    assert res is None
