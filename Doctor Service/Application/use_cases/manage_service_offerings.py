from uuid_extension import UUID7


class AddServiceOfferingUseCase:
    def __init__(self, service_repo):
        self.service_repo = service_repo

    async def execute(
        self, doctor_id: UUID7, service_name: str, duration_minutes: int, fee: float, description: str = None
    ):
        return await self.service_repo.create(doctor_id, service_name, duration_minutes, fee, description)


class UpdateServiceOfferingUseCase:
    def __init__(self, service_repo):
        self.service_repo = service_repo

    async def execute(self, service_id: UUID7, **kwargs):
        return await self.service_repo.update(service_id, **kwargs)


class ListServiceOfferingsUseCase:
    def __init__(self, service_repo):
        self.service_repo = service_repo

    async def execute(self, doctor_id: UUID7):
        return await self.service_repo.list_by_doctor(doctor_id)


class DeactivateServiceOfferingUseCase:
    def __init__(self, service_repo):
        self.service_repo = service_repo

    async def execute(self, service_id: UUID7):
        return await self.service_repo.deactivate(service_id)
