from datetime import date

from uuid_extension import UUID7


class AddDayOffUseCase:
    def __init__(self, day_off_repo):
        self.day_off_repo = day_off_repo

    async def execute(self, doctor_id: UUID7, off_date: date, reason: str = None):
        return await self.day_off_repo.create(doctor_id, off_date, reason)


class RemoveDayOffUseCase:
    def __init__(self, day_off_repo):
        self.day_off_repo = day_off_repo

    async def execute(self, doctor_id: UUID7, off_date: date):
        return await self.day_off_repo.delete(doctor_id, off_date)
