import logging

from healthai_events.consumer import BaseConsumer

logger = logging.getLogger(__name__)


class UserRegisteredConsumer(BaseConsumer):
    QUEUE = "patient_service_register_queue"
    EXCHANGE = "user_events"
    ROUTING_KEY = "user.registered"

    def __init__(self, connection, cache, session_factory):
        super().__init__(connection, cache)
        self._session_factory = session_factory

    async def handle(self, payload: dict):
        from Application import InitializeProfileUseCase, UserRegisteredHandler
        from infrastructure.repositories.repositories import PatientHealthRepository, PatientProfileRepository

        async with self._session_factory() as session:
            async with session.begin():
                profile_repo = PatientProfileRepository(session)
                health_repo = PatientHealthRepository(session)
                init_use_case = InitializeProfileUseCase(profile_repo, health_repo)
                handler = UserRegisteredHandler(init_use_case)
                await handler.handle(payload)
