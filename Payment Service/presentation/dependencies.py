from typing import Annotated

from Application.use_cases.create_payment import CreatePaymentFromEventUseCase
from Application.use_cases.handle_vnpay_ipn import ProcessVNPayIPnUseCase
from Application.use_cases.process_vnpay_ipn import GetPaymentUseCase
from Domain.interfaces import IEventPublisher, IPaymentProvider
from fastapi import Depends
from infrastructure.database.session import AsyncSessionLocal
from infrastructure.providers.vnpay_provider import VnpayProvider
from infrastructure.publishers.outbox_event_publisher import OutboxEventPublisher
from infrastructure.repositories.payment_repository import PaymentRepository
from sqlalchemy.ext.asyncio import AsyncSession


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


def get_payment_repo(session: Annotated[AsyncSession, Depends(get_session)]) -> PaymentRepository:
    return PaymentRepository(session)


def get_vnpay_provider() -> IPaymentProvider:
    return VnpayProvider()


def get_event_publisher() -> IEventPublisher:
    return OutboxEventPublisher()


def get_get_payment_use_case(
    repo: Annotated[PaymentRepository, Depends(get_payment_repo)],
) -> GetPaymentUseCase:
    return GetPaymentUseCase(repo)


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
