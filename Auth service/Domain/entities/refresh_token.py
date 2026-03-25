import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from uuid_extension import UUID7, uuid7


@dataclass
class RefreshToken:
    user_id: UUID7
    token_value: str
    expires_at: datetime

    is_revoked: bool = False
    revoked_at: Optional[datetime] = None
    replaced_by_token_id: UUID7 | None = None

    id: UUID7 = field(default_factory=uuid7)
    created_at: datetime = field(default_factory=datetime.now)
    last_used_at: Optional[datetime] = None

    def is_valid(self) -> bool:
        """Check if the refresh token is valid."""
        return not self.is_revoked and self.expires_at > datetime.now()

    def revoke(self, replaced_by_token_id: UUID7 | None = None):
        self.is_revoked = True
        self.revoked_at = datetime.now()
        self.replaced_by_token_id = replaced_by_token_id
        self.last_used_at = datetime.now()

    @staticmethod
    def generate_token(user_id: UUID7, expires_in: int = 30) -> "RefreshToken":
        return RefreshToken(
            user_id=user_id,
            token_value=secrets.token_urlsafe(64),
            expires_at=datetime.now() + timedelta(days=expires_in),
        )
