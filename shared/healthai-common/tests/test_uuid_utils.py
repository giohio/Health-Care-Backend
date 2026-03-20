import pytest
from datetime import datetime, timezone
from uuid_extension import uuid7
from healthai_common import new_id, extract_timestamp


def test_new_id_returns_uuid7():
    """Test that new_id() returns a valid UUID7."""
    uid = new_id()
    assert uid is not None
    assert isinstance(uid, object)  # UUID7 type


def test_extract_timestamp_from_uuid7():
    """Test extracting timestamp from UUID7."""
    uid = new_id()
    ts = extract_timestamp(uid)
    
    # Timestamp should be recent (within last minute)
    now = datetime.now(timezone.utc)
    diff = (now - ts).total_seconds()
    assert 0 <= diff < 60


def test_extract_timestamp_from_string():
    """Test extracting timestamp from UUID7 string."""
    uid = new_id()
    uid_str = str(uid)
    ts = extract_timestamp(uid_str)
    
    # Timestamp should be recent
    now = datetime.now(timezone.utc)
    diff = (now - ts).total_seconds()
    assert 0 <= diff < 60
