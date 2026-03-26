from uuid_extension import UUID7


class SetAvailabilityUseCase:
    def __init__(self, availability_repo):
        self.availability_repo = availability_repo

    async def execute(
        self,
        doctor_id: UUID7,
        day_of_week: int,
        start_time,
        end_time,
        break_start=None,
        break_end=None,
        max_patients=20,
    ):
        result = await self.availability_repo.upsert(
            doctor_id, day_of_week, start_time, end_time, break_start, break_end, max_patients
        )
        if hasattr(self.availability_repo, "session"):
            await self.availability_repo.session.commit()
        return result
