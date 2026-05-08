"""Repository for lab fee configuration."""
from uuid import UUID

from Domain.value_objects.lab_fee_config import LabFeeConfig
from infrastructure.database.models import LabFeeConfigModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class LabFeeConfigRepository:
    """Repository for managing lab fee configurations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _to_entity(model: LabFeeConfigModel) -> LabFeeConfig:
        return LabFeeConfig(
            id=model.id,
            test_id=model.test_id,
            test_name=model.test_name,
            fee=model.fee,
            currency=model.currency,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def save(self, config: LabFeeConfig) -> LabFeeConfig:
        """Create or update lab fee config."""
        stmt = select(LabFeeConfigModel).where(LabFeeConfigModel.test_id == config.test_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()

        if model:
            # Update existing
            model.test_name = config.test_name
            model.fee = config.fee
            model.currency = config.currency
        else:
            # Create new
            model = LabFeeConfigModel(
                id=config.id,
                test_id=config.test_id,
                test_name=config.test_name,
                fee=config.fee,
                currency=config.currency,
            )
            self.session.add(model)

        await self.session.flush()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def get_by_test_id(self, test_id: str) -> LabFeeConfig | None:
        """Fetch lab fee config by test_id."""
        stmt = select(LabFeeConfigModel).where(LabFeeConfigModel.test_id == test_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def list_all(self) -> list[LabFeeConfig]:
        """List all lab fee configs ordered by test_id."""
        stmt = select(LabFeeConfigModel).order_by(LabFeeConfigModel.test_id)
        result = await self.session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def delete(self, test_id: str) -> None:
        """Delete lab fee config by test_id."""
        stmt = select(LabFeeConfigModel).where(LabFeeConfigModel.test_id == test_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model:
            await self.session.delete(model)
            await self.session.flush()
