import pytest
from unittest.mock import AsyncMock, MagicMock
from healthai_common.saga import SagaOrchestrator, SagaFailedError, SagaState
from sqlalchemy.orm import Session

class MockSaga(SagaOrchestrator):
    SAGA_TYPE = "test_saga"
    STEPS = ["step1", "step2"]
    COMPENSATIONS = {"step1": "undo1"}

    async def execute_step1(self, ctx):
        ctx["step1_done"] = True
        return "result1"

    async def execute_step2(self, ctx):
        ctx["step2_done"] = True
        if ctx.get("fail_step2"):
            raise ValueError("Forced failure")
        return "result2"

    async def compensate_undo1(self, ctx):
        ctx["undone1"] = True

@pytest.fixture
def mock_session():
    session = MagicMock(spec=Session)
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session

@pytest.mark.asyncio
async def test_saga_failure_and_compensation(mock_session):
    orchestrator = MockSaga(mock_session, MagicMock())
    payload = {"data": "input", "fail_step2": True}
    
    # Run the saga and expect it to fail
    with pytest.raises(SagaFailedError):
        await orchestrator.run(payload)
    
    # The saga object was added to session
    assert mock_session.add.called
    saga_obj = mock_session.add.call_args[0][0]
    
    print(f"DEBUG: saga_obj.status={saga_obj.status}")
    print(f"DEBUG: saga_obj.completed_steps={saga_obj.completed_steps}")
    print(f"DEBUG: saga_obj.compensated_steps={saga_obj.compensated_steps}")

    assert saga_obj.status == "failed"
    assert "step1" in saga_obj.completed_steps
    assert "step1" in saga_obj.compensated_steps
