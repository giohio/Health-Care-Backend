from uuid_extension import UUID7


class GetAvailabilityUseCase:
    def __init__(self, availability_repo):
        self.availability_repo = availability_repo

    async def execute(self, doctor_id: UUID7):
        return await self.availability_repo.get_by_doctor(doctor_id)
