from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


@dataclass
class PaymentRequest:
    order_id: UUID
    amount: int
    order_desc: str
    return_url: str
    client_ip: str


@dataclass
class PaymentResult:
    success: bool
    provider_ref: str | None
    failure_reason: str | None = None


class IPaymentProvider(ABC):
    @abstractmethod
    async def create_payment_url(self, request: PaymentRequest) -> str:
        raise NotImplementedError

    @abstractmethod
    def verify_callback(self, params: dict) -> PaymentResult:
        raise NotImplementedError
