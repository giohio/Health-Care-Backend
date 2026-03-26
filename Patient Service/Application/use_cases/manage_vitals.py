from uuid_extension import UUID7


class RecordVitalsUseCase:
    def __init__(self, vitals_repo, session=None, initialize_use_case=None):
        self.vitals_repo = vitals_repo
        self.session = session
        self.initialize_use_case = initialize_use_case

    async def execute(self, patient_id: UUID7, recorded_by: UUID7, **vitals_data):
        if self.initialize_use_case:
            # Ensure profile (and health background) exists before recording vitals
            # patient_id here is the user_id
            await self.initialize_use_case.execute(patient_id)

        return await self.vitals_repo.create(patient_id, recorded_by, vitals_data)


class GetLatestVitalsUseCase:
    def __init__(self, vitals_repo, initialize_use_case=None):
        self.vitals_repo = vitals_repo
        self.initialize_use_case = initialize_use_case

    async def execute(self, patient_id: UUID7):
        if self.initialize_use_case:
            await self.initialize_use_case.execute(patient_id)
        return await self.vitals_repo.get_latest(patient_id)


class GetVitalsHistoryUseCase:
    def __init__(self, vitals_repo, initialize_use_case=None):
        self.vitals_repo = vitals_repo
        self.initialize_use_case = initialize_use_case

    async def execute(self, patient_id: UUID7, page: int = 1, limit: int = 20):
        if self.initialize_use_case:
            await self.initialize_use_case.execute(patient_id)
        offset = (page - 1) * limit
        return await self.vitals_repo.list_by_patient(patient_id, limit, offset)
