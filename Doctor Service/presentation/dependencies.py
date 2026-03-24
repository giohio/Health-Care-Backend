from typing import Annotated

from Application.use_cases.list_specialties import ListSpecialtiesUseCase
from Application.use_cases.register_doctor import RegisterDoctorUseCase
from Application.use_cases.save_specialty import SaveSpecialtyUseCase
from Application.use_cases.search_available_doctors import SearchAvailableDoctorsUseCase
from Application.use_cases.set_auto_confirm_settings import SetAutoConfirmSettingsUseCase
from Application.use_cases.update_doctor_profile import UpdateDoctorProfileUseCase
from Application.use_cases.update_schedule import UpdateScheduleUseCase
from Domain.interfaces.event_publisher import IEventPublisher
from fastapi import Depends
from infrastructure.database.session import get_db
from infrastructure.publishers.outbox_event_publisher import OutboxEventPublisher
from infrastructure.repositories import DoctorRepository, ScheduleRepository, SpecialtyRepository
from sqlalchemy.ext.asyncio import AsyncSession


# Publishers
def get_event_publisher(session: Annotated[AsyncSession, Depends(get_db)]) -> IEventPublisher:
    return OutboxEventPublisher(session)


# Repositories
def get_specialty_repo(session: Annotated[AsyncSession, Depends(get_db)]):
    return SpecialtyRepository(session)


def get_doctor_repo(session: Annotated[AsyncSession, Depends(get_db)]):
    return DoctorRepository(session)


def get_schedule_repo(session: Annotated[AsyncSession, Depends(get_db)]):
    return ScheduleRepository(session)


# Use Cases
def get_list_specialties_use_case(repo: Annotated[SpecialtyRepository, Depends(get_specialty_repo)]):
    return ListSpecialtiesUseCase(repo)


def get_save_specialty_use_case(repo: Annotated[SpecialtyRepository, Depends(get_specialty_repo)]):
    return SaveSpecialtyUseCase(repo)


def get_register_doctor_use_case(repo: Annotated[DoctorRepository, Depends(get_doctor_repo)]):
    return RegisterDoctorUseCase(repo)


def get_update_doctor_profile_use_case(
    repo: Annotated[DoctorRepository, Depends(get_doctor_repo)],
    event_publisher: Annotated[IEventPublisher, Depends(get_event_publisher)],
):
    return UpdateDoctorProfileUseCase(repo, event_publisher)


def get_update_schedule_use_case(
    schedule_repo: Annotated[ScheduleRepository, Depends(get_schedule_repo)],
    doctor_repo: Annotated[DoctorRepository, Depends(get_doctor_repo)],
):
    return UpdateScheduleUseCase(schedule_repo, doctor_repo)


def get_search_available_doctors_use_case(repo: Annotated[DoctorRepository, Depends(get_doctor_repo)]):
    return SearchAvailableDoctorsUseCase(repo)


def get_set_auto_confirm_settings_use_case(repo: Annotated[DoctorRepository, Depends(get_doctor_repo)]):
    return SetAutoConfirmSettingsUseCase(repo)
