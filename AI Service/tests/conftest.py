import pytest
from Domain.entities import PatientContext


@pytest.fixture
def patient_context():
    return PatientContext(
        patient_id="p-001",
        full_name="Nguyễn Văn A",
        age=45,
        gender="male",
        active_diagnoses=["Tăng huyết áp"],
        current_medications=["Amlodipine 5mg"],
        allergies="Penicillin",
        chronic_conditions="Tiểu đường type 2",
    )
