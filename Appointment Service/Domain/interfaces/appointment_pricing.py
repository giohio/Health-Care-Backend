from abc import ABC, abstractmethod


class IAppointmentPricingPolicy(ABC):
    @abstractmethod
    def default_amount_vnd(self) -> int:
        raise NotImplementedError
