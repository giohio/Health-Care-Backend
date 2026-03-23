import pytest
from healthai_events import NonRetryableError, RetryableError


def test_retryable_error_is_exception():
    """Test that RetryableError can be raised and caught."""
    with pytest.raises(RetryableError):
        raise RetryableError("Network timeout")


def test_non_retryable_error_is_exception():
    """Test that NonRetryableError can be raised and caught."""
    with pytest.raises(NonRetryableError):
        raise NonRetryableError("Invalid payload")
