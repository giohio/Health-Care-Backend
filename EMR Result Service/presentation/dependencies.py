from functools import lru_cache
from typing import Annotated

from Application.use_cases.claim_lab_result import ClaimLabResultUseCase
from Application.use_cases.create_lab_order import CreateLabOrderUseCase
from Application.use_cases.delete_lab_order import DeleteLabOrderUseCase
from Application.use_cases.flag_manual_review import FlagManualReviewUseCase
from Application.use_cases.get_lab_readiness import GetLabReadinessUseCase
from Application.use_cases.get_lab_results import GetLabResultUseCase, ListLabResultsUseCase
from Application.use_cases.holistic_summary import GetHolisticSummaryUseCase, UpdateHolisticSummaryUseCase, ReviewHolisticSummaryUseCase
from Application.use_cases.lab_order_template import (
    CreateLabOrderTemplateUseCase,
    CreateOrdersFromTemplateUseCase,
    DeleteLabOrderTemplateUseCase,
    ListLabOrderTemplatesUseCase,
)
from Application.use_cases.list_lab_orders import ListLabOrdersUseCase
from Application.use_cases.update_ai_draft import UpdateAIDraftUseCase
from Application.use_cases.upload_file import UploadFileUseCase
from Application.use_cases.upload_lab_result import UploadLabResultUseCase
from Application.use_cases.verify_and_publish import VerifyAndPublishUseCase
from fastapi import Depends, Request
from healthai_cache import CacheClient
from infrastructure.clients.ai_service_client import AiServiceClient
from infrastructure.clients.external_clients import ClinicalServiceClient, NotificationClient, PatientServiceClient
from infrastructure.config import settings
from infrastructure.database.session import get_db
from infrastructure.repositories import AppointmentSummaryRepository, LabOrderRepository, LabOrderTemplateRepository, LabResultRepository
from infrastructure.storage import LocalFileStorage
from sqlalchemy.ext.asyncio import AsyncSession


def get_db_session(session: Annotated[AsyncSession, Depends(get_db)]) -> AsyncSession:
    return session


@lru_cache()
def get_cache_client() -> CacheClient:
    return CacheClient.from_url(settings.REDIS_URL)


def get_order_repo(session: Annotated[AsyncSession, Depends(get_db_session)]):
    return LabOrderRepository(session)


def get_result_repo(session: Annotated[AsyncSession, Depends(get_db_session)]):
    return LabResultRepository(session)


def get_summary_repo(session: Annotated[AsyncSession, Depends(get_db_session)]):
    return AppointmentSummaryRepository(session)


def get_template_repo(session: Annotated[AsyncSession, Depends(get_db_session)]):
    return LabOrderTemplateRepository(session)


def get_notification_client(cache: Annotated[CacheClient, Depends(get_cache_client)]):
    return NotificationClient(cache=cache)


def get_clinical_client(cache: Annotated[CacheClient, Depends(get_cache_client)]):
    return ClinicalServiceClient(cache=cache)


def get_patient_service_client(cache: Annotated[CacheClient, Depends(get_cache_client)]):
    return PatientServiceClient(cache=cache)


def get_event_publisher(request: Request):
    """Return the EmrEventPublisher stored on app.state (set during startup)."""
    return getattr(request.app.state, "event_publisher", None)


# ---------------------------------------------------------------------------
# Use case factories
# ---------------------------------------------------------------------------


def get_create_order_use_case(
    request: Request,
    order_repo: Annotated[LabOrderRepository, Depends(get_order_repo)],
):
    publisher = getattr(request.app.state, "event_publisher", None)
    return CreateLabOrderUseCase(order_repo, event_publisher=publisher)


def get_list_orders_use_case(
    order_repo: Annotated[LabOrderRepository, Depends(get_order_repo)],
):
    return ListLabOrdersUseCase(order_repo)


def get_upload_result_use_case(
    order_repo: Annotated[LabOrderRepository, Depends(get_order_repo)],
    result_repo: Annotated[LabResultRepository, Depends(get_result_repo)],
):
    return UploadLabResultUseCase(order_repo, result_repo)


def get_list_results_use_case(
    result_repo: Annotated[LabResultRepository, Depends(get_result_repo)],
):
    return ListLabResultsUseCase(result_repo)


def get_result_use_case(
    result_repo: Annotated[LabResultRepository, Depends(get_result_repo)],
):
    return GetLabResultUseCase(result_repo)


def get_verify_publish_use_case(
    request: Request,
    result_repo: Annotated[LabResultRepository, Depends(get_result_repo)],
    order_repo: Annotated[LabOrderRepository, Depends(get_order_repo)],
    notification_client: Annotated[NotificationClient, Depends(get_notification_client)],
    clinical_client: Annotated[ClinicalServiceClient, Depends(get_clinical_client)],
    summary_repo: Annotated[AppointmentSummaryRepository, Depends(get_summary_repo)],
):
    publisher = getattr(request.app.state, "event_publisher", None)
    return VerifyAndPublishUseCase(
        result_repo, order_repo, notification_client, clinical_client,
        event_publisher=publisher,
        summary_repo=summary_repo,
        ai_service_client=AiServiceClient(),
    )


def get_readiness_use_case(
    order_repo: Annotated[LabOrderRepository, Depends(get_order_repo)],
    result_repo: Annotated[LabResultRepository, Depends(get_result_repo)],
):
    return GetLabReadinessUseCase(order_repo, result_repo)


def get_flag_manual_review_use_case(
    result_repo: Annotated[LabResultRepository, Depends(get_result_repo)],
):
    return FlagManualReviewUseCase(result_repo)


@lru_cache()
def get_file_storage() -> LocalFileStorage:
    return LocalFileStorage(settings.UPLOAD_DIR, settings.UPLOAD_BASE_URL)


def get_upload_file_use_case() -> UploadFileUseCase:
    return UploadFileUseCase(get_file_storage(), settings.MAX_UPLOAD_BYTES)


def get_ai_service_client() -> AiServiceClient:
    return AiServiceClient()


def get_get_holistic_summary_use_case(
    summary_repo: Annotated[AppointmentSummaryRepository, Depends(get_summary_repo)],
) -> GetHolisticSummaryUseCase:
    return GetHolisticSummaryUseCase(summary_repo)


def get_update_holistic_summary_use_case(
    summary_repo: Annotated[AppointmentSummaryRepository, Depends(get_summary_repo)],
) -> UpdateHolisticSummaryUseCase:
    return UpdateHolisticSummaryUseCase(summary_repo)


def get_review_holistic_summary_use_case(
    summary_repo: Annotated[AppointmentSummaryRepository, Depends(get_summary_repo)],
) -> ReviewHolisticSummaryUseCase:
    return ReviewHolisticSummaryUseCase(summary_repo)


def get_update_ai_draft_use_case(
    result_repo: Annotated[LabResultRepository, Depends(get_result_repo)],
    order_repo: Annotated[LabOrderRepository, Depends(get_order_repo)],
) -> UpdateAIDraftUseCase:
    return UpdateAIDraftUseCase(result_repo, order_repo)


def get_claim_lab_result_use_case(
    result_repo: Annotated[LabResultRepository, Depends(get_result_repo)],
) -> ClaimLabResultUseCase:
    return ClaimLabResultUseCase(result_repo)


def get_create_order_template_use_case(
    template_repo: Annotated[LabOrderTemplateRepository, Depends(get_template_repo)],
) -> CreateLabOrderTemplateUseCase:
    return CreateLabOrderTemplateUseCase(template_repo)


def get_list_order_templates_use_case(
    template_repo: Annotated[LabOrderTemplateRepository, Depends(get_template_repo)],
) -> ListLabOrderTemplatesUseCase:
    return ListLabOrderTemplatesUseCase(template_repo)


def get_delete_order_template_use_case(
    template_repo: Annotated[LabOrderTemplateRepository, Depends(get_template_repo)],
) -> DeleteLabOrderTemplateUseCase:
    return DeleteLabOrderTemplateUseCase(template_repo)


def get_delete_order_use_case(
    request: Request,
    order_repo: Annotated[LabOrderRepository, Depends(get_order_repo)],
    result_repo: Annotated[LabResultRepository, Depends(get_result_repo)],
) -> DeleteLabOrderUseCase:
    publisher = getattr(request.app.state, "event_publisher", None)
    return DeleteLabOrderUseCase(order_repo, result_repo, event_publisher=publisher)


def get_create_orders_from_template_use_case(
    template_repo: Annotated[LabOrderTemplateRepository, Depends(get_template_repo)],
    order_repo: Annotated[LabOrderRepository, Depends(get_order_repo)],
) -> CreateOrdersFromTemplateUseCase:
    return CreateOrdersFromTemplateUseCase(template_repo, order_repo)