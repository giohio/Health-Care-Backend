from typing import Annotated, AsyncGenerator

from Application.use_cases.create_payment import CreatePaymentFromEventUseCase
from Application.use_cases.generate_payment_url import GeneratePaymentUrlUseCase
from Application.use_cases.generate_lab_order_payment_url import GenerateLabOrderPaymentUrlUseCase
from Application.use_cases.generate_bulk_lab_order_payment_url import GenerateBulkLabOrderPaymentUrlUseCase
from Application.use_cases.list_admin_payment_history import ListAdminPaymentHistoryUseCase
from Application.use_cases.handle_vnpay_ipn import ProcessVNPayIPnUseCase
from Application.use_cases.list_patient_payments import ListPatientPaymentsUseCase
from Application.use_cases.list_patient_payment_history import ListPatientPaymentHistoryUseCase
from Application.use_cases.process_vnpay_ipn import GetPaymentUseCase
from Application.use_cases.mark_payment_refunded import MarkPaymentRefundedUseCase
from Application.use_cases.list_lab_fee_configs import ListLabFeeConfigsUseCase
from Application.use_cases.update_lab_fee_config import UpdateLabFeeConfigUseCase
from Domain.interfaces import IEventPublisher, IPaymentProvider
from fastapi import Depends, Request
from infrastructure.database.session import AsyncSessionLocal
from infrastructure.providers.vnpay_provider import VnpayProvider
from infrastructure.publishers.outbox_event_publisher import OutboxEventPublisher
from infrastructure.repositories.payment_repository import PaymentRepository
from infrastructure.repositories.lab_fee_config_repository import LabFeeConfigRepository
from sqlalchemy.ext.asyncio import AsyncSession


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


def get_payment_repo(session: Annotated[AsyncSession, Depends(get_session)]) -> PaymentRepository:
    return PaymentRepository(session)


def get_lab_fee_config_repo(session: Annotated[AsyncSession, Depends(get_session)]) -> LabFeeConfigRepository:
    return LabFeeConfigRepository(session)


def get_vnpay_provider() -> IPaymentProvider:
    return VnpayProvider()


def get_event_publisher() -> IEventPublisher:
    return OutboxEventPublisher()


def get_get_payment_use_case(
    repo: Annotated[PaymentRepository, Depends(get_payment_repo)],
) -> GetPaymentUseCase:
    return GetPaymentUseCase(repo)


def get_list_patient_payments_use_case(
    repo: Annotated[PaymentRepository, Depends(get_payment_repo)],
) -> ListPatientPaymentsUseCase:
    return ListPatientPaymentsUseCase(repo)


def get_list_patient_payment_history_use_case(
    repo: Annotated[PaymentRepository, Depends(get_payment_repo)],
) -> ListPatientPaymentHistoryUseCase:
    return ListPatientPaymentHistoryUseCase(repo)


def get_list_admin_payment_history_use_case(
    repo: Annotated[PaymentRepository, Depends(get_payment_repo)],
) -> ListAdminPaymentHistoryUseCase:
    return ListAdminPaymentHistoryUseCase(repo)


def get_generate_payment_url_use_case(
    session: Annotated[AsyncSession, Depends(get_session)],
    repo: Annotated[PaymentRepository, Depends(get_payment_repo)],
    vnpay: Annotated[IPaymentProvider, Depends(get_vnpay_provider)],
) -> GeneratePaymentUrlUseCase:
    return GeneratePaymentUrlUseCase(session, repo, vnpay)


def get_generate_lab_order_payment_url_use_case(
    session: Annotated[AsyncSession, Depends(get_session)],
    repo: Annotated[PaymentRepository, Depends(get_payment_repo)],
    vnpay: Annotated[IPaymentProvider, Depends(get_vnpay_provider)],
) -> GenerateLabOrderPaymentUrlUseCase:
    return GenerateLabOrderPaymentUrlUseCase(session, repo, vnpay)


def get_generate_bulk_lab_order_payment_url_use_case(
    session: Annotated[AsyncSession, Depends(get_session)],
    repo: Annotated[PaymentRepository, Depends(get_payment_repo)],
    vnpay: Annotated[IPaymentProvider, Depends(get_vnpay_provider)],
    event_publisher: Annotated[IEventPublisher, Depends(get_event_publisher)],
) -> GenerateBulkLabOrderPaymentUrlUseCase:
    return GenerateBulkLabOrderPaymentUrlUseCase(session, repo, vnpay, event_publisher)


def get_create_payment_use_case(
    session: Annotated[AsyncSession, Depends(get_session)],
    repo: Annotated[PaymentRepository, Depends(get_payment_repo)],
    vnpay: Annotated[IPaymentProvider, Depends(get_vnpay_provider)],
    event_publisher: Annotated[IEventPublisher, Depends(get_event_publisher)],
) -> CreatePaymentFromEventUseCase:
    return CreatePaymentFromEventUseCase(session, repo, vnpay, event_publisher)


def get_process_vnpay_ipn_use_case(
    session: Annotated[AsyncSession, Depends(get_session)],
    repo: Annotated[PaymentRepository, Depends(get_payment_repo)],
    vnpay: Annotated[IPaymentProvider, Depends(get_vnpay_provider)],
    event_publisher: Annotated[IEventPublisher, Depends(get_event_publisher)],
) -> ProcessVNPayIPnUseCase:
    return ProcessVNPayIPnUseCase(session, repo, vnpay, event_publisher)


def get_mark_payment_refunded_use_case(
    session: Annotated[AsyncSession, Depends(get_session)],
    repo: Annotated[PaymentRepository, Depends(get_payment_repo)],
    event_publisher: Annotated[IEventPublisher, Depends(get_event_publisher)],
) -> MarkPaymentRefundedUseCase:
    return MarkPaymentRefundedUseCase(session, repo, event_publisher)


def get_list_lab_fee_configs_use_case(
    repo: Annotated[LabFeeConfigRepository, Depends(get_lab_fee_config_repo)],
) -> ListLabFeeConfigsUseCase:
    return ListLabFeeConfigsUseCase(repo)


def get_update_lab_fee_config_use_case(
    repo: Annotated[LabFeeConfigRepository, Depends(get_lab_fee_config_repo)],
) -> UpdateLabFeeConfigUseCase:
    return UpdateLabFeeConfigUseCase(repo)
