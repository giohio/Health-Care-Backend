from Domain.interfaces.doctor_repository import IDoctorRepository
from Domain.interfaces.rating_repository import IRatingRepository
from uuid_extension import UUID7


class SubmitRatingUseCase:
    def __init__(self, rating_repo: IRatingRepository, doctor_repo: IDoctorRepository, appointment_repo):
        self.rating_repo = rating_repo
        self.doctor_repo = doctor_repo
        self.appointment_repo = appointment_repo

    async def execute(
        self,
        doctor_id: UUID7,
        patient_id: UUID7,
        rating: int,
        comment: str | None = None,
        appointment_id: UUID7 | None = None,
    ):
        # Verify patient has completed appointment with doctor
        if appointment_id:
            appt = await self.appointment_repo.get_by_id(appointment_id)
            if not appt:
                raise ValueError("Invalid appointment for rating")

            # Robust comparison (convert both to string to ensure type consistency)
            appt_patient_id = str(appt.patient_id)
            req_patient_id = str(patient_id)
            appt_doctor_id = str(appt.doctor_id)
            req_doctor_id = str(doctor_id)

            if appt_patient_id != req_patient_id or appt_doctor_id != req_doctor_id or appt.status != "COMPLETED":
                raise ValueError("Invalid appointment for rating")
        else:
            has_completed = await self.appointment_repo.has_completed_appointment(patient_id, doctor_id)
            if not has_completed:
                raise ValueError("Can only rate after completed appointment")

        # Check if already rated
        existing = await self.rating_repo.get_by_patient_and_doctor(patient_id, doctor_id)
        if existing:
            raise ValueError("Already rated this doctor")

        # Save rating
        rating_entity = await self.rating_repo.create(doctor_id, patient_id, rating, comment)

        # Recalculate average
        avg = await self.rating_repo.get_average_rating(doctor_id)
        if avg is not None:
            await self.doctor_repo.update_average_rating(doctor_id, avg)

        return rating_entity
