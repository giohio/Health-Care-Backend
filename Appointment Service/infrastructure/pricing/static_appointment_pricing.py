from Domain.interfaces import IAppointmentPricingPolicy
from infrastructure.config import settings


class StaticAppointmentPricingPolicy(IAppointmentPricingPolicy):
    def default_amount_vnd(self) -> int:
        return int(settings.DEFAULT_APPOINTMENT_AMOUNT_VND)
