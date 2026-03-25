from abc import ABC, abstractmethod


class IEmailSender(ABC):
    @abstractmethod
    async def send_email(self, to: str, subject: str, body: str) -> None:
        pass
