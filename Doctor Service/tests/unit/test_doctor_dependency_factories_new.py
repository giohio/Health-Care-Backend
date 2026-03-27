import pytest
from unittest.mock import MagicMock
from presentation.dependencies import (
    get_specialty_repo, get_doctor_repo, get_schedule_repo,
    get_list_specialties_use_case, get_register_doctor_use_case,
    get_rating_repo, get_appointment_repo, get_submit_rating_use_case,
    get_availability_repo, get_day_off_repo, get_service_offering_repo,
    get_enhanced_schedule_use_case
)
from infrastructure.repositories import SpecialtyRepository, DoctorRepository, ScheduleRepository
from Application.use_cases.list_specialties import ListSpecialtiesUseCase
from Application.use_cases.register_doctor import RegisterDoctorUseCase
from Application.use_cases.get_enhanced_schedule import GetEnhancedScheduleUseCase

def test_repository_factories():
    session = MagicMock()
    assert isinstance(get_specialty_repo(session), SpecialtyRepository)
    assert isinstance(get_doctor_repo(session), DoctorRepository)
    assert isinstance(get_schedule_repo(session), ScheduleRepository)

def test_use_case_factories():
    repo = MagicMock()
    cache = MagicMock()
    assert isinstance(get_list_specialties_use_case(repo, cache), ListSpecialtiesUseCase)
    assert isinstance(get_register_doctor_use_case(repo), RegisterDoctorUseCase)

def test_new_repository_factories():
    session = MagicMock()
    # RatingRepository and others are imported inside functions
    from infrastructure.repositories.rating_repository import RatingRepository
    from infrastructure.repositories.availability_repository import AvailabilityRepository
    from infrastructure.repositories.day_off_repository import DayOffRepository
    from infrastructure.repositories.service_offering_repository import ServiceOfferingRepository
    from infrastructure.repositories.appointment_repository import AppointmentRepository

    assert isinstance(get_rating_repo(session), RatingRepository)
    assert isinstance(get_availability_repo(session), AvailabilityRepository)
    assert isinstance(get_day_off_repo(session), DayOffRepository)
    assert isinstance(get_service_offering_repo(session), ServiceOfferingRepository)
    assert isinstance(get_appointment_repo(), AppointmentRepository)

def test_complex_use_case_factories():
    availability_repo = MagicMock()
    day_off_repo = MagicMock()
    service_offering_repo = MagicMock()
    cache = MagicMock()
    
    uc = get_enhanced_schedule_use_case(availability_repo, day_off_repo, service_offering_repo, cache)
    assert isinstance(uc, GetEnhancedScheduleUseCase)
    assert uc.availability_repo == availability_repo
    assert uc.day_off_repo == day_off_repo
    assert uc.service_offering_repo == service_offering_repo

def test_submit_rating_use_case_factory():
    rating_repo = MagicMock()
    doctor_repo = MagicMock()
    appointment_repo = MagicMock()
    cache = MagicMock()
    
    from Application.use_cases.submit_rating import SubmitRatingUseCase
    uc = get_submit_rating_use_case(rating_repo, doctor_repo, appointment_repo, cache)
    assert isinstance(uc, SubmitRatingUseCase)
