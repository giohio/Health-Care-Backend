from Domain.interfaces.external_clients import IClinicalServiceClient, INotificationClient
from Domain.interfaces.lab_order_repository import ILabOrderRepository
from Domain.interfaces.lab_result_repository import ILabResultRepository

__all__ = [
    "IClinicalServiceClient",
    "ILabOrderRepository",
    "ILabResultRepository",
    "INotificationClient",
]
