from Domain.interfaces.rating_repository import IRatingRepository
from uuid_extension import UUID7


class ListRatingsUseCase:
    def __init__(self, rating_repo: IRatingRepository):
        self.rating_repo = rating_repo

    async def execute(self, doctor_id: UUID7, page: int = 1, limit: int = 20):
        offset = (page - 1) * limit
        ratings = await self.rating_repo.list_by_doctor(doctor_id, limit, offset)
        return ratings
