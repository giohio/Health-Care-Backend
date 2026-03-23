import re
from typing import List, Tuple


class PasswordValidator:
    MIN_LENGTH = 8
    MAX_LENGTH = 20

    @staticmethod
    def validate(password: str) -> Tuple[bool, List[str]]:
        errors = []

        if len(password) < PasswordValidator.MIN_LENGTH:
            errors.append(f"Password must be at least {PasswordValidator.MIN_LENGTH} characters")

        if len(password) > PasswordValidator.MAX_LENGTH:
            errors.append(f"Password must not exceed {PasswordValidator.MAX_LENGTH} characters")

        if not re.search(r"[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter")

        if not re.search(r"[a-z]", password):
            errors.append("Password must contain at least one lowercase letter")

        if not re.search(r"\d", password):
            errors.append("Password must contain at least one digit")

        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")

        return len(errors) == 0, errors
