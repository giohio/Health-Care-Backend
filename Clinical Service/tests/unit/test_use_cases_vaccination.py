import uuid
from datetime import date

from Application.use_cases.list_vaccinations import ListVaccinationsUseCase
from tests.conftest import FakeVaccinationRepo, make_vaccination


class TestListVaccinations:
    def setup_method(self):
        self.repo = FakeVaccinationRepo()
        self.use_case = ListVaccinationsUseCase(self.repo)

    async def test_lists_vaccinations_for_patient(self):
        patient_id = uuid.uuid4()
        await self.repo.save(make_vaccination(patient_id=patient_id, vaccine_name="COVID-19", date_administered=date(2025, 1, 1)))
        await self.repo.save(make_vaccination(patient_id=patient_id, vaccine_name="Influenza", date_administered=date(2025, 2, 1)))
        await self.repo.save(make_vaccination(patient_id=uuid.uuid4(), vaccine_name="HPV"))

        results = await self.use_case.execute(patient_id)

        assert len(results) == 2
        assert results[0].vaccine_name == "Influenza"

    async def test_empty_patient_returns_empty(self):
        results = await self.use_case.execute(uuid.uuid4())
        assert results == []