"""Unit tests for Domain exceptions — covers domain_exceptions.py."""
import pytest

from Domain.exceptions.domain_exceptions import (
    EMRDomainError,
    InvalidLabResultStatusTransitionError,
    LabOrderNotFoundError,
    LabResultNotFoundError,
    ResultNotPublishedError,
    UnauthorizedEMRActionError,
)


class TestDomainExceptions:
    def test_lab_order_not_found_is_exception(self):
        exc = LabOrderNotFoundError()
        assert isinstance(exc, Exception)
        assert "not found" in str(exc).lower()

    def test_lab_result_not_found_is_exception(self):
        exc = LabResultNotFoundError()
        assert isinstance(exc, Exception)
        assert "not found" in str(exc).lower()

    def test_invalid_transition_includes_states(self):
        exc = InvalidLabResultStatusTransitionError("PENDING", "PUBLISHED")
        msg = str(exc)
        assert "PENDING" in msg
        assert "PUBLISHED" in msg

    def test_result_not_published_message(self):
        exc = ResultNotPublishedError()
        assert "published" in str(exc).lower()

    def test_unauthorized_emr_action_message(self):
        exc = UnauthorizedEMRActionError()
        assert "unauthorized" in str(exc).lower()

    def test_all_inherit_from_base(self):
        for cls in (
            LabOrderNotFoundError,
            LabResultNotFoundError,
            InvalidLabResultStatusTransitionError,
            ResultNotPublishedError,
            UnauthorizedEMRActionError,
        ):
            assert issubclass(cls, EMRDomainError)

    def test_base_inherits_from_exception(self):
        assert issubclass(EMRDomainError, Exception)

    def test_can_raise_and_catch_as_base(self):
        with pytest.raises(EMRDomainError):
            raise LabOrderNotFoundError()

    def test_can_raise_and_catch_as_base_result(self):
        with pytest.raises(EMRDomainError):
            raise LabResultNotFoundError()

    def test_invalid_transition_can_raise(self):
        with pytest.raises(InvalidLabResultStatusTransitionError):
            raise InvalidLabResultStatusTransitionError("AI_PROCESSING", "PENDING")
