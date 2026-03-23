import re
from typing import Optional


class EmailValidator:
    EMAIL_REGEX = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

    @staticmethod
    def is_valid(email: str) -> bool:
        if not email or not isinstance(email, str):
            return False

        email = email.strip().lower()

        if not re.match(EmailValidator.EMAIL_REGEX, email):
            return False

        if len(email) > 254:
            return False

        local_part, _ = email.rsplit("@", 1)

        if len(local_part) > 64:
            return False

        return True

    @staticmethod
    def get_domain(email: str) -> Optional[str]:
        try:
            return email.split("@")[1].lower()
        except (IndexError, AttributeError):
            return None
