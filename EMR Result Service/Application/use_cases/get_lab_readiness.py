"""Use case: get lab readiness status for an appointment.

Returns how many lab orders have been fulfilled (result published) out of the
total for a given appointment.  Used by the Appointment Service to enrich the
doctor queue with lab readiness information.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID
import logging

from Domain.interfaces.lab_order_repository import ILabOrderRepository
from Domain.interfaces.lab_result_repository import ILabResultRepository
from Domain.value_objects.lab_result_status import LabResultStatus

logger = logging.getLogger(__name__)


class GetLabReadinessUseCase:
    def __init__(
        self,
        order_repo: ILabOrderRepository,
        result_repo: ILabResultRepository,
    ) -> None:
        self.order_repo = order_repo
        self.result_repo = result_repo

    async def execute(self, appointment_id: UUID) -> dict[str, Any]:
        orders = await self.order_repo.list_by_appointment_id(appointment_id)
        total = len(orders)

        if total == 0:
            return {
                "appointment_id": str(appointment_id),
                "total_orders": 0,
                "completed_results": 0,
                "all_ready": True,
                "results": [],
            }

        order_ids = [o.id for o in orders]
        results = await self.result_repo.list_by_order_ids(order_ids)

        published = [r for r in results if r.status == LabResultStatus.PUBLISHED]
        all_ready = len(published) == total

        results_summary = [
            {
                "result_id": str(r.id),
                "order_id": str(r.order_id),
                "status": r.status.value,
            }
            for r in results
        ]

        return {
            "appointment_id": str(appointment_id),
            "total_orders": total,
            "completed_results": len(published),
            "all_ready": all_ready,
            "results": results_summary,
        }
