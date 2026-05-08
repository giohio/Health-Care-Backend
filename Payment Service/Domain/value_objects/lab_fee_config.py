"""Lab fee configuration value object."""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class LabFeeConfig:
    """Lab fee configuration domain model."""

    id: UUID
    test_id: str
    test_name: str
    fee: int  # in VND
    currency: str = "VND"
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "id": str(self.id),
            "test_id": self.test_id,
            "test_name": self.test_name,
            "fee": self.fee,
            "currency": self.currency,
        }
