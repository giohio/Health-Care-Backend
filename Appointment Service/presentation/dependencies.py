from functools import lru_cache
from typing import Annotated

from Application.use_cases.book_appointment import BookAppointmentUseCase
from Application.use_cases.cancel_appointment import CancelAppointmentUseCase
from Application.use_cases.complete_appointment import CompleteAppointmentUseCase
from Application.use_cases.confirm_appointment import ConfirmAppointmentUseCase
from Application.use_cases.decline_appointment import DeclineAppointmentUseCase
from Application.use_cases.get_available_slots import GetAvailableSlotsUseCase
from Application.use_cases.get_doctor_queue import GetDoctorQueueUseCase
from Application.use_cases.list_patient_appointments import ListPatientAppointmentsUseCase
from Application.use_cases.mark_no_show import MarkNoShowUseCase
from Application.use_cases.reschedule_appointment import RescheduleAppointmentUseCase
from fastapi import Depends
from healthai_cache import CacheClient
from infrastructure.cache.redis_lock_manager import RedisLockManager
from infrastructure.clients.doctor_service_client import DoctorServiceClient
from infrastructure.config import settings
from infrastructure.database.session import get_db
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


def get_book_appointment_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    cache: Annotated[CacheClient, Depends(get_cache_client)],
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repo)],
    doctor_client: Annotated[DoctorServiceClient, Depends(get_doctor_client)],
    lock_manager: Annotated[RedisLockManager, Depends(get_lock_manager)],
):
    return BookAppointmentUseCase(session, cache, lock_manager, repo, doctor_client)


def get_list_appointments_use_case(repo: Annotated[AppointmentRepository, Depends(get_appointment_repo)]):
    return ListPatientAppointmentsUseCase(repo)


def get_cancel_appointment_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repo)],
):
    return CancelAppointmentUseCase(session, repo)


def get_confirm_appointment_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repo)],
):
    return ConfirmAppointmentUseCase(session, repo)


def get_decline_appointment_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repo)],
):
    return DeclineAppointmentUseCase(session, repo)


def get_reschedule_appointment_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repo)],
    doctor_client: Annotated[DoctorServiceClient, Depends(get_doctor_client)],
    lock_manager: Annotated[RedisLockManager, Depends(get_lock_manager)],
):
    return RescheduleAppointmentUseCase(session, lock_manager, repo, doctor_client)


def get_complete_appointment_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repo)],
):
    return CompleteAppointmentUseCase(session, repo)


def get_mark_no_show_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repo)],
):
    return MarkNoShowUseCase(session, repo)


def get_available_slots_use_case(
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repo)],
    doctor_client: Annotated[DoctorServiceClient, Depends(get_doctor_client)],
):
    return GetAvailableSlotsUseCase(repo, doctor_client)


def get_doctor_queue_use_case(
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repo)],
    doctor_client: Annotated[DoctorServiceClient, Depends(get_doctor_client)],
):
    return GetDoctorQueueUseCase(repo, doctor_client)
