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


def get_rating_repo(session: Annotated[AsyncSession, Depends(get_db)]):
    from infrastructure.repositories.rating_repository import RatingRepository

    return RatingRepository(session)


def get_appointment_repo():
    from infrastructure.clients.appointment_service_client import AppointmentServiceClient
    from infrastructure.repositories.appointment_repository import AppointmentRepository

    return AppointmentRepository(AppointmentServiceClient())


def get_submit_rating_use_case(
    rating_repo=Depends(get_rating_repo),
    doctor_repo=Depends(get_doctor_repo),
    appointment_repo=Depends(get_appointment_repo),
):
    from Application.use_cases.submit_rating import SubmitRatingUseCase

    return SubmitRatingUseCase(rating_repo, doctor_repo, appointment_repo)


def get_list_ratings_use_case(rating_repo=Depends(get_rating_repo)):
    from Application.use_cases.list_ratings import ListRatingsUseCase

    return ListRatingsUseCase(rating_repo)


def get_availability_repo(session: Annotated[AsyncSession, Depends(get_db)]):
    from infrastructure.repositories.availability_repository import AvailabilityRepository

    return AvailabilityRepository(session)


def get_day_off_repo(session: Annotated[AsyncSession, Depends(get_db)]):
    from infrastructure.repositories.day_off_repository import DayOffRepository

    return DayOffRepository(session)


def get_service_offering_repo(session: Annotated[AsyncSession, Depends(get_db)]):
    from infrastructure.repositories.service_offering_repository import ServiceOfferingRepository

    return ServiceOfferingRepository(session)


def get_set_availability_use_case(repo=Depends(get_availability_repo)):
    from Application.use_cases.set_availability import SetAvailabilityUseCase

    return SetAvailabilityUseCase(repo)


def get_get_availability_use_case(repo=Depends(get_availability_repo)):
    from Application.use_cases.get_availability import GetAvailabilityUseCase

    return GetAvailabilityUseCase(repo)


def get_add_day_off_use_case(repo=Depends(get_day_off_repo)):
    from Application.use_cases.manage_day_off import AddDayOffUseCase

    return AddDayOffUseCase(repo)


def get_remove_day_off_use_case(repo=Depends(get_day_off_repo)):
    from Application.use_cases.manage_day_off import RemoveDayOffUseCase

    return RemoveDayOffUseCase(repo)


def get_add_service_offering_use_case(repo=Depends(get_service_offering_repo)):
    from Application.use_cases.manage_service_offerings import AddServiceOfferingUseCase

    return AddServiceOfferingUseCase(repo)


def get_update_service_offering_use_case(repo=Depends(get_service_offering_repo)):
    from Application.use_cases.manage_service_offerings import UpdateServiceOfferingUseCase

    return UpdateServiceOfferingUseCase(repo)


def get_list_service_offerings_use_case(repo=Depends(get_service_offering_repo)):
    from Application.use_cases.manage_service_offerings import ListServiceOfferingsUseCase

    return ListServiceOfferingsUseCase(repo)


def get_deactivate_service_offering_use_case(repo=Depends(get_service_offering_repo)):
    from Application.use_cases.manage_service_offerings import DeactivateServiceOfferingUseCase

    return DeactivateServiceOfferingUseCase(repo)


def get_enhanced_schedule_use_case(
    availability_repo=Depends(get_availability_repo),
    day_off_repo=Depends(get_day_off_repo),
    service_offering_repo=Depends(get_service_offering_repo),
):
    from Application.use_cases.get_enhanced_schedule import GetEnhancedScheduleUseCase

    return GetEnhancedScheduleUseCase(availability_repo, day_off_repo, service_offering_repo)
