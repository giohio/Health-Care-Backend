"""Use case: Update lab fee configuration."""
from uuid import uuid4

from Domain.value_objects.lab_fee_config import LabFeeConfig
from infrastructure.repositories.lab_fee_config_repository import LabFeeConfigRepository


class UpdateLabFeeConfigUseCase:
    """Update a lab fee configuration."""

    def __init__(self, repo: LabFeeConfigRepository):
        self.repo = repo

    async def execute(self, test_id: str, fee: int) -> dict:
        """
        Update fee for a lab test.

        Args:
            test_id: The test identifier.
            fee: The new fee in VND.

        Returns:
            Updated lab fee config as dictionary.

        Raises:
            ValueError: If test_id not found.
        """
        config = await self.repo.get_by_test_id(test_id)
        if not config:
            raise ValueError(f"Lab fee config for test_id '{test_id}' not found")

        # Create updated entity
        updated_config = LabFeeConfig(
            id=config.id,
            test_id=config.test_id,
            test_name=config.test_name,
            fee=fee,
            currency=config.currency,
        )

        # Save and return
        saved = await self.repo.save(updated_config)
        return saved.to_dict()
