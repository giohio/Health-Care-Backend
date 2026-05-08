"""Use case: List all lab fee configurations."""
from infrastructure.repositories.lab_fee_config_repository import LabFeeConfigRepository


class ListLabFeeConfigsUseCase:
    """Retrieve all lab fee configurations."""

    def __init__(self, repo: LabFeeConfigRepository):
        self.repo = repo

    async def execute(self) -> list[dict]:
        """
        List all lab fee configurations.

        Returns:
            List of lab fee configs as dictionaries.
        """
        configs = await self.repo.list_all()
        return [config.to_dict() for config in configs]
