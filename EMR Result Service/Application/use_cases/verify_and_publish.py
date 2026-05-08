import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from Application.dtos import LabResultResponse, VerifyLabResultRequest
from Application.exceptions import LabResultNotFoundError, UnauthorizedReviewerError
from Domain.entities.appointment_lab_summary import AppointmentLabSummary, AppointmentSummaryStatus
from Domain.interfaces.appointment_summary_repository import IAppointmentSummaryRepository
from Domain.interfaces.external_clients import IClinicalServiceClient, INotificationClient
from Domain.interfaces.lab_order_repository import ILabOrderRepository
from Domain.interfaces.lab_result_repository import ILabResultRepository
from Domain.value_objects.lab_result_status import LabResultStatus

logger = logging.getLogger(__name__)


class VerifyAndPublishUseCase:
    """Doctor verifies the AI draft and publishes the result to the patient.

    Side effects (all best-effort, non-blocking failures):
      1. Writes a clinical note to clinical_service.
      2. Sends a push notification to the patient via notification_service.
      3. Publishes ``lab_result.published`` event.
      4. If all results for the same appointment are now PUBLISHED, creates an
         AppointmentLabSummary record and triggers the holistic AI analysis.
    """

    def __init__(
        self,
        result_repo: ILabResultRepository,
        order_repo: ILabOrderRepository,
        notification_client: INotificationClient,
        clinical_client: IClinicalServiceClient,
        event_publisher=None,
        summary_repo: Optional[IAppointmentSummaryRepository] = None,
        ai_service_client=None,
    ):
        self.result_repo = result_repo
        self.order_repo = order_repo
        self.notification_client = notification_client
        self.clinical_client = clinical_client
        self._publisher = event_publisher
        self._summary_repo = summary_repo
        self._ai_client = ai_service_client

    async def execute(
        self,
        result_id: uuid.UUID,
        doctor_id: uuid.UUID,
        request: VerifyLabResultRequest,
        caller_role: str = "doctor",
    ) -> LabResultResponse:
        result = await self.result_repo.get_by_id(result_id)
        if result is None:
            raise LabResultNotFoundError()

        # Enforce reviewer assignment — admins bypass this check
        if caller_role != "admin" and result.reviewer_doctor_id is not None:
            if result.reviewer_doctor_id != doctor_id:
                raise UnauthorizedReviewerError()

        now = datetime.now(tz=timezone.utc)

        result.publish(
            verified_by=doctor_id,
            verified_at=now,
            published_at=now,
            doctor_notes=request.doctor_notes,
            published_text=request.published_text,
            published_findings=request.published_findings,
        )

        saved = await self.result_repo.save(result)

        # Fetch order to get test_name for notification message
        order = await self.order_repo.get_by_id(saved.order_id)
        test_name = order.test_name if order else "lab test"

        # Side effects — errors are logged, not raised
        await self.notification_client.send_lab_result_ready(
            patient_id=saved.patient_id,
            result_id=saved.id,
            test_name=test_name,
        )
        await self.clinical_client.push_lab_result_to_record(
            patient_id=saved.patient_id,
            doctor_id=doctor_id,
            result_id=saved.id,
            order_id=saved.order_id,
            test_name=test_name,
            published_text=saved.published_text,
            published_findings=saved.published_findings,
        )

        # Emit lab_result.published event
        if self._publisher is not None:
            try:
                await self._publisher.publish(
                    event_type="lab_result.published",
                    payload={
                        "result_id": str(saved.id),
                        "order_id": str(saved.order_id),
                        "patient_id": str(saved.patient_id),
                        "doctor_id": str(doctor_id),
                        "test_name": test_name,
                    },
                )
            except Exception:
                logger.exception("Failed to publish lab_result.published for result %s", saved.id)

            # Check if all orders for this appointment have published results
            logger.info("Checking: order=%s, order.appointment_id=%s", order, order.appointment_id if order else None)
            
            if order and order.appointment_id:
                try:
                    logger.info("Calling _check_all_results_ready for appointment %s", order.appointment_id)
                    await self._check_all_results_ready(
                        appointment_id=order.appointment_id,
                        patient_id=saved.patient_id,
                    )
                except Exception:
                    logger.exception(
                        "Failed to check all_results_ready for appointment %s", order.appointment_id
                    )
            else:
                logger.warning("Order or appointment_id missing: order=%s", order)

        return LabResultResponse.model_validate(saved, from_attributes=True)

    async def _check_all_results_ready(self, appointment_id: uuid.UUID, patient_id: uuid.UUID) -> None:
        """Emit lab_order.all_results_ready and trigger holistic AI analysis if all results published."""
        orders = await self.order_repo.list_by_appointment_id(appointment_id)
        logger.info("_check_all_results_ready: appointment %s has %d orders", appointment_id, len(orders))

        if not orders:
            logger.info("No orders for appointment %s", appointment_id)
            return

        order_ids = [o.id for o in orders]
        results = await self.result_repo.list_by_order_ids(order_ids)
        logger.info("Found %d results total", len(results))

        published_ids = {r.order_id for r in results if r.status == LabResultStatus.PUBLISHED}
        logger.info("Published order IDs: %s", published_ids)

        if published_ids != set(order_ids):
            logger.info("Not all results ready yet for appointment %s", appointment_id)
            return

        logger.info("All results published for appointment %s — triggering holistic analysis", appointment_id)

        # Emit event (best-effort)
        if self._publisher is not None:
            try:
                await self._publisher.publish(
                    event_type="lab_order.all_results_ready",
                    payload={
                        "appointment_id": str(appointment_id),
                        "patient_id": str(patient_id),
                        "total_results": len(order_ids),
                    },
                )
            except Exception:
                logger.exception("Failed to publish lab_order.all_results_ready for appointment %s", appointment_id)

        # Create/upsert AppointmentLabSummary and dispatch holistic Celery task
        if self._summary_repo is not None and self._ai_client is not None:
            try:
                # Idempotent: if already exists we overwrite to PENDING to re-trigger
                existing = await self._summary_repo.get_by_appointment_id(appointment_id)
                if existing and existing.status == AppointmentSummaryStatus.DONE:
                    # Already done — skip re-trigger to avoid redundant expensive calls
                    logger.info("Holistic summary already DONE for appointment %s — skipping", appointment_id)
                    return

                summary = AppointmentLabSummary(
                    id=existing.id if existing else uuid.uuid4(),
                    appointment_id=appointment_id,
                    patient_id=patient_id,
                    status=AppointmentSummaryStatus.PENDING,
                    ai_holistic_text=None,
                    total_results=len(order_ids),
                )
                saved = await self._summary_repo.save(summary)
                await self._ai_client.trigger_holistic_analysis(
                    appointment_id=appointment_id,
                    patient_id=patient_id,
                    summary_id=saved.id,
                )
            except Exception:
                logger.exception("Failed to trigger holistic analysis for appointment %s", appointment_id)
