from functools import lru_cache
from typing import Annotated

from Application.use_cases.book_appointment import BookAppointmentUseCase
from Application.use_cases.cancel_appointment import CancelAppointmentUseCase
from Application.use_cases.complete_appointment import CompleteAppointmentUseCase
from Application.use_cases.confirm_appointment import ConfirmAppointmentUseCase
from Application.use_cases.decline_appointment import DeclineAppointmentUseCase
from Application.use_cases.get_appointment_stats import GetAppointmentStatsUseCase
from Application.use_cases.get_available_slots import GetAvailableSlotsUseCase
from Application.use_cases.get_doctor_queue import GetDoctorQueueUseCase
from Application.use_cases.list_doctor_appointments import ListDoctorAppointmentsUseCase
from Application.use_cases.list_patient_appointments import ListPatientAppointmentsUseCase
from Application.use_cases.mark_no_show import MarkNoShowUseCase
from Application.use_cases.reschedule_appointment import RescheduleAppointmentUseCase
from Application.use_cases.start_appointment import StartAppointmentUseCase
from Domain.interfaces.appointment_pricing import IAppointmentPricingPolicy
from Domain.interfaces.event_publisher import IEventPublisher
from fastapi import Depends
from healthai_cache import CacheClient
from infrastructure.cache.redis_lock_manager import RedisLockManager
from infrastructure.clients.doctor_service_client import DoctorServiceClient
from infrastructure.config import settings
from infrastructure.database.session import get_db
from infrastructure.pricing.static_appointment_pricing import StaticAppointmentPricingPolicy
from infrastructure.publishers.outbox_event_publisher import OutboxEventPublisher
from infrastructure.repositories import AppointmentRepository
from sqlalchemy.ext.asyncio import AsyncSession


def get_db_session(session: Annotated[AsyncSession, Depends(get_db)]) -> AsyncSession:
    return session


@lru_cache()
def get_cache_client() -> CacheClient:
    return CacheClient.from_url(settings.REDIS_URL)


def get_appointment_repo(session: Annotated[AsyncSession, Depends(get_db_session)]):
    return AppointmentRepository(session)


def get_doctor_client(cache: Annotated[CacheClient, Depends(get_cache_client)]):
    return DoctorServiceClient(cache=cache)


def get_lock_manager(cache: Annotated[CacheClient, Depends(get_cache_client)]):
    return RedisLockManager(cache=cache)


def get_event_publisher() -> IEventPublisher:
    return OutboxEventPublisher()


def get_pricing_policy() -> IAppointmentPricingPolicy:
    return StaticAppointmentPricingPolicy()


def get_book_appointment_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    cache: Annotated[CacheClient, Depends(get_cache_client)],
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repo)],
    doctor_client: Annotated[DoctorServiceClient, Depends(get_doctor_client)],
    lock_manager: Annotated[RedisLockManager, Depends(get_lock_manager)],
    event_publisher: Annotated[IEventPublisher, Depends(get_event_publisher)],
    pricing_policy: Annotated[IAppointmentPricingPolicy, Depends(get_pricing_policy)],
):
    return BookAppointmentUseCase(session, cache, lock_manager, repo, doctor_client, event_publisher, pricing_policy)


def get_list_appointments_use_case(repo: Annotated[AppointmentRepository, Depends(get_appointment_repo)]):
    return ListPatientAppointmentsUseCase(repo)


def get_list_doctor_appointments_use_case(repo: Annotated[AppointmentRepository, Depends(get_appointment_repo)]):
    return ListDoctorAppointmentsUseCase(repo)


def get_cancel_appointment_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repo)],
    event_publisher: Annotated[IEventPublisher, Depends(get_event_publisher)],
    cache: Annotated[CacheClient, Depends(get_cache_client)],
):
    return CancelAppointmentUseCase(session, repo, event_publisher, cache)


def get_confirm_appointment_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repo)],
    event_publisher: Annotated[IEventPublisher, Depends(get_event_publisher)],
):
    return ConfirmAppointmentUseCase(session, repo, event_publisher)


def get_start_appointment_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repo)],
    event_publisher: Annotated[IEventPublisher, Depends(get_event_publisher)],
):
    return StartAppointmentUseCase(session, repo, event_publisher)


def get_decline_appointment_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repo)],
    event_publisher: Annotated[IEventPublisher, Depends(get_event_publisher)],
):
    return DeclineAppointmentUseCase(session, repo, event_publisher)


def get_reschedule_appointment_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repo)],
    doctor_client: Annotated[DoctorServiceClient, Depends(get_doctor_client)],
    lock_manager: Annotated[RedisLockManager, Depends(get_lock_manager)],
    event_publisher: Annotated[IEventPublisher, Depends(get_event_publisher)],
    cache: Annotated[CacheClient, Depends(get_cache_client)],
):
    return RescheduleAppointmentUseCase(session, lock_manager, repo, doctor_client, event_publisher, cache)


def get_complete_appointment_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repo)],
    event_publisher: Annotated[IEventPublisher, Depends(get_event_publisher)],
):
    return CompleteAppointmentUseCase(session, repo, event_publisher)


def get_mark_no_show_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repo)],
    event_publisher: Annotated[IEventPublisher, Depends(get_event_publisher)],
    cache: Annotated[CacheClient, Depends(get_cache_client)],
):
    return MarkNoShowUseCase(session, repo, event_publisher, cache)


def get_available_slots_use_case(
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repo)],
    doctor_client: Annotated[DoctorServiceClient, Depends(get_doctor_client)],
    cache: Annotated[CacheClient, Depends(get_cache_client)],
):
    return GetAvailableSlotsUseCase(repo, doctor_client, cache)


def get_doctor_queue_use_case(
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repo)],
    doctor_client: Annotated[DoctorServiceClient, Depends(get_doctor_client)],
    cache: Annotated[CacheClient, Depends(get_cache_client)],
):
    return GetDoctorQueueUseCase(repo, doctor_client, cache)


def get_appointment_stats_use_case(repo: Annotated[AppointmentRepository, Depends(get_appointment_repo)]):
    return GetAppointmentStatsUseCase(repo)
