from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from infrastructure.database.session import get_db
from infrastructure.repositories import AppointmentRepository
from infrastructure.clients.doctor_service_client import DoctorServiceClient
from Application.use_cases.book_appointment import BookAppointmentUseCase
from Application.use_cases.list_patient_appointments import ListPatientAppointmentsUseCase
from Application.use_cases.cancel_appointment import CancelAppointmentUseCase
from typing import Annotated
from functools import lru_cache
from Domain.interfaces import IAppointmentRepository, IDoctorServiceClient, ILockManager, IEventPublisher
from infrastructure.cache.redis_lock_manager import RedisLockManager
from infrastructure.config import settings
from shared_lib.messaging.publisher import BasePublisher


# Repositories & Clients
def get_appointment_repo(session: Annotated[AsyncSession, Depends(get_db)]):
    return AppointmentRepository(session)

def get_doctor_client():
    return DoctorServiceClient()

# Use Cases
def get_book_appointment_use_case(
    repo: Annotated[AppointmentRepository, Depends(get_appointment_repo)],
    client: Annotated[DoctorServiceClient, Depends(get_doctor_client)]
):
    return BookAppointmentUseCase(repo, client)

def get_list_appointments_use_case(repo: Annotated[AppointmentRepository, Depends(get_appointment_repo)]):
    return ListPatientAppointmentsUseCase(repo)

def get_cancel_appointment_use_case(repo: Annotated[AppointmentRepository, Depends(get_appointment_repo)]):
    return CancelAppointmentUseCase(repo)

@lru_cache()
def get_lock_manager() -> ILockManager:
    return RedisLockManager(settings.REDIS_URL)

@lru_cache()
def get_event_publisher() -> IEventPublisher:
    return BasePublisher(settings.RABBITMQ_URL)

def get_book_appointment_use_case(
    repo: IAppointmentRepository = Depends(get_appointment_repo),
    doctor_client: IDoctorServiceClient = Depends(get_doctor_client),
    lock_manager: ILockManager = Depends(get_lock_manager),
    event_publisher: IEventPublisher = Depends(get_event_publisher)
):
    return BookAppointmentUseCase(repo, doctor_client, lock_manager, event_publisher)