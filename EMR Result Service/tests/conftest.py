"""Shared test fixtures for EMR Result Service unit tests."""
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pytest_asyncio

from Domain.entities.lab_order import LabOrder
from Domain.entities.lab_result import LabResult
from Domain.interfaces.external_clients import IClinicalServiceClient, INotificationClient, IPatientServiceClient
from Domain.interfaces.lab_order_repository import ILabOrderRepository
from Domain.interfaces.lab_result_repository import ILabResultRepository
from Domain.value_objects.lab_result_status import LabResultStatus
from Domain.value_objects.order_priority import OrderPriority
from Domain.value_objects.test_type import TestType


# ---------------------------------------------------------------------------
# Fake repositories
# ---------------------------------------------------------------------------


class FakeLabOrderRepo(ILabOrderRepository):
    def __init__(self):
        self._store: Dict[uuid.UUID, LabOrder] = {}

    async def save(self, order: LabOrder) -> LabOrder:
        self._store[order.id] = order
        return order

    async def get_by_id(self, order_id: uuid.UUID) -> Optional[LabOrder]:
        return self._store.get(order_id)

    async def list(
        self,
        patient_id: Optional[uuid.UUID] = None,
        doctor_id: Optional[uuid.UUID] = None,
    ) -> List[LabOrder]:
        results = list(self._store.values())
        if patient_id is not None:
            results = [o for o in results if o.patient_id == patient_id]
        if doctor_id is not None:
            results = [o for o in results if o.doctor_id == doctor_id]
        return results

    async def list_by_appointment_id(self, appointment_id: uuid.UUID) -> List[LabOrder]:
        return [order for order in self._store.values() if order.appointment_id == appointment_id]

    async def delete(self, order_id: uuid.UUID) -> None:
        if order_id not in self._store:
            raise ValueError("Lab order not found")
        del self._store[order_id]


class FakeLabResultRepo(ILabResultRepository):
    def __init__(self):
        self._store: Dict[uuid.UUID, LabResult] = {}

    async def save(self, result: LabResult) -> LabResult:
        self._store[result.id] = result
        return result

    async def get_by_id(self, result_id: uuid.UUID) -> Optional[LabResult]:
        return self._store.get(result_id)

    async def list(
        self,
        patient_id: Optional[uuid.UUID] = None,
        doctor_id: Optional[uuid.UUID] = None,
        status: Optional[LabResultStatus] = None,
        reviewer_doctor_id: Optional[uuid.UUID] = None,
        required_specialty: Optional[str] = None,
        open_claim: Optional[bool] = None,
    ) -> List[LabResult]:
        results = list(self._store.values())
        if patient_id is not None:
            results = [r for r in results if r.patient_id == patient_id]
        if doctor_id is not None:
            results = [r for r in results if r.doctor_id == doctor_id]
        if status is not None:
            results = [r for r in results if r.status == status]
        if reviewer_doctor_id is not None:
            results = [r for r in results if r.reviewer_doctor_id == reviewer_doctor_id]
        if required_specialty is not None:
            results = [r for r in results if r.required_specialty == required_specialty]
        if open_claim is True:
            results = [
                r for r in results
                if r.required_specialty is not None and r.reviewer_doctor_id is None
            ]
        return results

    async def list_by_order_ids(self, order_ids: List[uuid.UUID]) -> List[LabResult]:
        order_id_set = set(order_ids)
        return [result for result in self._store.values() if result.order_id in order_id_set]

    async def delete(self, result_id: uuid.UUID) -> None:
        if result_id not in self._store:
            raise ValueError("Lab result not found")
        del self._store[result_id]


# ---------------------------------------------------------------------------
# Fake external clients
# ---------------------------------------------------------------------------


class FakeNotificationClient(INotificationClient):
    def __init__(self):
        self.calls: List[Dict] = []

    async def send_lab_result_ready(
        self,
        patient_id: uuid.UUID,
        result_id: uuid.UUID,
        test_name: str,
    ) -> None:
        self.calls.append({"patient_id": patient_id, "result_id": result_id, "test_name": test_name})


class FakeClinicalClient(IClinicalServiceClient):
    def __init__(self):
        self.calls: List[Dict] = []

    async def push_lab_result_to_record(
        self,
        patient_id: uuid.UUID,
        doctor_id: uuid.UUID,
        result_id: uuid.UUID,
        order_id: uuid.UUID,
        test_name: str,
        published_text: Optional[str],
        published_findings: Optional[Dict],
    ) -> None:
        self.calls.append({"patient_id": patient_id, "result_id": result_id})


class FakePatientServiceClient(IPatientServiceClient):
    def __init__(self, name: str = "Nguyen Van A"):
        self.name = name

    async def get_patient_name(self, patient_id: uuid.UUID) -> Optional[str]:
        return self.name


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

NOW = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)


def make_lab_order(**kwargs) -> LabOrder:
    defaults = dict(
        id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        doctor_id=uuid.uuid4(),
        test_name="Complete Blood Count",
        test_type=TestType.BLOOD_PANEL,
        priority=OrderPriority.ROUTINE,
        ordered_at=NOW,
    )
    defaults.update(kwargs)
    return LabOrder(**defaults)


def make_lab_result(**kwargs) -> LabResult:
    defaults = dict(
        id=uuid.uuid4(),
        order_id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        doctor_id=uuid.uuid4(),
        status=LabResultStatus.PENDING,
        file_url="s3://bucket/result.pdf",
        file_type="application/pdf",
    )
    defaults.update(kwargs)
    return LabResult(**defaults)
