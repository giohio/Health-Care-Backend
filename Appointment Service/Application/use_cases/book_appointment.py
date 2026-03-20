from uuid_extension import UUID7
from uuid import UUID
from datetime import datetime, timedelta, time
from Domain.entities.appointment import Appointment
from Domain.interfaces import (
    IAppointmentRepository, 
    IDoctorServiceClient, 
    ILockManager,
    IEventPublisher
)
from Domain.exceptions.domain_exceptions import NoDoctorAvailableException
from Application.dtos import CreateAppointmentRequest, AppointmentResponse
import logging

logger = logging.getLogger(__name__)

class BookAppointmentUseCase:
    def __init__(
        self, 
        appointment_repo: IAppointmentRepository,
        doctor_client: IDoctorServiceClient,
        lock_manager: ILockManager,
        event_publisher: IEventPublisher
    ):
        self.appointment_repo = appointment_repo
        self.doctor_client = doctor_client
        self.lock_manager = lock_manager
        self.event_publisher = event_publisher

    async def execute(self, request: CreateAppointmentRequest) -> AppointmentResponse:
        # 1. Get day of week (0-6)
        day_of_week = request.appointment_date.weekday()
        
        # 2. Get doctors from Doctor Service
        available_doctors = await self.doctor_client.get_available_doctors(
            specialty_id=request.specialty_id,
            day_of_week=day_of_week,
            time_slot=request.start_time
        )
        
        if not available_doctors:
            raise NoDoctorAvailableException()

        # 3. Check for actual availability (not booked)
        selected_doctor_id = None
        for doc in available_doctors:
            doc_id = UUID(doc["user_id"])
            is_free = await self.appointment_repo.check_doctor_availability(
                doctor_id=doc_id,
                appointment_date=request.appointment_date,
                start_time=request.start_time
            )
            if is_free:
                selected_doctor_id = doc_id
                break
        
        if not selected_doctor_id:
            raise NoDoctorAvailableException()

        lock_key = f"lock:slot:{selected_doctor_id}:{request.appointment_date}:{request.start_time}"

        is_locked = await self.lock_manager.acquire_lock(lock_key, 15)
        if not is_locked:
            raise HTTPException(status_code=409, detail="Slot is locked")
        
        try:
             # 4. Create appointment (Assuming 30 min duration for simplicity)
            start_datetime = datetime.combine(request.appointment_date, request.start_time)
            end_datetime = start_datetime + timedelta(minutes=30)
            
            appointment = Appointment(
                id=UUID7(),
                patient_id=request.patient_id,
                doctor_id=selected_doctor_id,
                specialty_id=request.specialty_id,
                appointment_date=request.appointment_date,
                start_time=request.start_time,
                end_time=end_datetime.time()
            )
            
            await self.appointment_repo.save(appointment)
            
            try:
                await self.event_publisher.publish(
                    exchange_name="appointment_events",
                    routing_key="appointment.check_timeout",
                    message={"appointment_id": str(appointment.id)},
                    delay_ms=60000  # 1 minute for testing, change to 900000 for 15 minutes later
                )
                logger.info(f"Published check_timeout event for appointment {appointment.id}")
            except Exception as e:
                logger.error(f"Failed to publish check_timeout event: {str(e)}")
            
            return AppointmentResponse.model_validate(appointment)

        finally:
            await self.lock_manager.release_lock(lock_key)

       