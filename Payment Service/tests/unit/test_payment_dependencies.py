import pytest

from Application.use_cases.create_payment import CreatePaymentFromEventUseCase
from Application.use_cases.handle_vnpay_ipn import ProcessVNPayIPnUseCase
from Application.use_cases.process_vnpay_ipn import GetPaymentUseCase
from infrastructure.providers.vnpay_provider import VnpayProvider
from infrastructure.publishers.outbox_event_publisher import OutboxEventPublisher
from infrastructure.repositories.payment_repository import PaymentRepository
from presentation import dependencies


def test_factory_functions_return_expected_types():
    fake_session = object()
    repo = dependencies.get_payment_repo(fake_session)
    assert isinstance(repo, PaymentRepository)

    vnpay = dependencies.get_vnpay_provider()
    assert isinstance(vnpay, VnpayProvider)

    publisher = dependencies.get_event_publisher()
    assert isinstance(publisher, OutboxEventPublisher)


def test_use_case_factories_wire_dependencies():
    session = object()
    repo = PaymentRepository(session)
    vnpay = VnpayProvider()
    publisher = OutboxEventPublisher()

    get_uc = dependencies.get_get_payment_use_case(repo)
    assert isinstance(get_uc, GetPaymentUseCase)

    create_uc = dependencies.get_create_payment_use_case(session, repo, vnpay, publisher)
    assert isinstance(create_uc, CreatePaymentFromEventUseCase)

    ipn_uc = dependencies.get_process_vnpay_ipn_use_case(session, repo, vnpay, publisher)
    assert isinstance(ipn_uc, ProcessVNPayIPnUseCase)


@pytest.mark.asyncio
async def test_get_session_yields_from_async_session_local(monkeypatch):
    sentinel = object()

    class FakeSessionFactory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return sentinel

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(dependencies, "AsyncSessionLocal", FakeSessionFactory())

    agen = dependencies.get_session()
    yielded = await anext(agen)
    assert yielded is sentinel
    await agen.aclose()
