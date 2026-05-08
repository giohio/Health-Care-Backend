import asyncio

from pwdlib import PasswordHash


class PasswordHasher:
    def __init__(self):
        self.pwd_context = PasswordHash.recommended()

    async def hash(self, password: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.pwd_context.hash, password)

    async def verify(self, plain_password: str, hashed_password: str) -> bool:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.pwd_context.verify, plain_password, hashed_password)
