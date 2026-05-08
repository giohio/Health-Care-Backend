"""Unit tests for Domain exceptions and Diagnosis entity methods."""
import uuid
from datetime import date

import pytest

from Domain.exceptions.domain_exceptions import (
    ClinicalDomainError,
    ClinicalNoteNotFoundError,
    DiagnosisNotFoundError,
    InvalidDiagnosisStatusTransitionError,
    InvalidMedicationStatusTransitionError,
    MedicationNotFoundError,
    UnauthorizedClinicalActionError,
)
from Domain.entities.diagnosis import Diagnosis
from Domain.value_objects.diagnosis_status import DiagnosisStatus
from Domain.value_objects.record_source import RecordSource


# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------


class TestDomainExceptions:
    def test_diagnosis_not_found_is_clinical_domain_error(self):
        exc = DiagnosisNotFoundError()
        assert isinstance(exc, ClinicalDomainError)
        assert "not found" in str(exc).lower()

    def test_medication_not_found_is_clinical_domain_error(self):
        exc = MedicationNotFoundError()
        assert isinstance(exc, ClinicalDomainError)
        assert "not found" in str(exc).lower()

    def test_clinical_note_not_found_is_clinical_domain_error(self):
        exc = ClinicalNoteNotFoundError()
        assert isinstance(exc, ClinicalDomainError)
        assert "not found" in str(exc).lower()

    def test_invalid_medication_status_transition_message(self):
        exc = InvalidMedicationStatusTransitionError("active", "discontinued")
        assert isinstance(exc, ClinicalDomainError)
        assert "active" in str(exc)
        assert "discontinued" in str(exc)

    def test_invalid_diagnosis_status_transition_message(self):
        exc = InvalidDiagnosisStatusTransitionError("active", "resolved")
        assert isinstance(exc, ClinicalDomainError)
        assert "active" in str(exc)
        assert "resolved" in str(exc)

    def test_unauthorized_clinical_action_message(self):
        exc = UnauthorizedClinicalActionError()
        assert isinstance(exc, ClinicalDomainError)
        assert "unauthorized" in str(exc).lower()

    def test_all_exceptions_inherit_exception(self):
        for exc_class in [
            DiagnosisNotFoundError,
            MedicationNotFoundError,
            ClinicalNoteNotFoundError,
            UnauthorizedClinicalActionError,
        ]:
            assert issubclass(exc_class, Exception)


# ---------------------------------------------------------------------------
# Diagnosis.resolve() and mark_chronic() error branches
# ---------------------------------------------------------------------------


def _make_diagnosis(**kwargs) -> Diagnosis:
    defaults = {
        "id": uuid.uuid4(),
        "patient_id": uuid.uuid4(),
        "doctor_id": uuid.uuid4(),
        "diagnosis_name": "Hypertension",
        "diagnosed_at": date(2025, 1, 10),
        "status": DiagnosisStatus.ACTIVE,
        "source": RecordSource.DOCTOR,
    }
    defaults.update(kwargs)
    return Diagnosis(**defaults)


class TestDiagnosisEntity:
    def test_resolve_active_diagnosis_succeeds(self):
        d = _make_diagnosis(status=DiagnosisStatus.ACTIVE)
        d.resolve(date(2025, 6, 1))
        assert d.status == DiagnosisStatus.RESOLVED
        assert d.resolved_at == date(2025, 6, 1)

    def test_resolve_chronic_diagnosis_raises(self):
        d = _make_diagnosis(status=DiagnosisStatus.CHRONIC)
        with pytest.raises(ValueError, match="Chronic"):
            d.resolve(date(2025, 6, 1))

    def test_resolve_already_resolved_raises(self):
        d = _make_diagnosis(status=DiagnosisStatus.RESOLVED)
        with pytest.raises(ValueError, match="already resolved"):
            d.resolve(date(2025, 6, 1))

    def test_mark_chronic_active_diagnosis_succeeds(self):
        d = _make_diagnosis(status=DiagnosisStatus.ACTIVE)
        d.mark_chronic()
        assert d.status == DiagnosisStatus.CHRONIC

    def test_mark_chronic_non_active_raises(self):
        d = _make_diagnosis(status=DiagnosisStatus.RESOLVED)
        with pytest.raises(ValueError, match="Only active"):
            d.mark_chronic()
