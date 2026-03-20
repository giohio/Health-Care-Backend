from datetime import datetime, timedelta
from typing import Dict, Any
import jwt
from jwt.exceptions import PyJWTError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from uuid_extension import UUID7
from Domain import UserRole

private_key_path = "private.pem"


class JWTHandler:
    def __init__(self):
        self.load_private_key()

    def load_private_key(self) -> str:
        try:
            with open(private_key_path, "r") as key_file:
                private_key = key_file.read()
        except FileNotFoundError:
            raise FileNotFoundError("Private key not found")

        self.private_key = private_key

        private_key_pem = serialization.load_pem_private_key(
            private_key.encode(),
            password=None,
            backend=default_backend()
        )

        self.public_key = private_key_pem.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

    def create_access_token(
        self,
        user_id: UUID7,
        role: UserRole,
        is_profile_completed: bool,
        expires_in: int = 15
    ) -> str:
        payload = {
            "user_id": str(user_id),
            "role": role,
            "is_profile_completed": is_profile_completed,
            "exp": datetime.now() + timedelta(minutes=expires_in),
            "iss": "healthcare-system-issuer"
        }
        return jwt.encode(payload, self.private_key, algorithm="RS256")

    def decode_access_token(self, token: str) -> Dict[str, Any]:
        try:
            return jwt.decode(token, self.public_key, algorithms=["RS256"])
        except PyJWTError as e:
            raise ValueError(str(e))
