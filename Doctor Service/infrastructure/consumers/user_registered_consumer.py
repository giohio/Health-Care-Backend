import logging

from healthai_events.consumer import BaseConsumer

logger = logging.getLogger(__name__)


class UserRegisteredConsumer(BaseConsumer):
    QUEUE = "doctor_service_user_queue"
    EXCHANGE = "user_events"
    ROUTING_KEY = "user.registered"

    def __init__(self, connection, cache, session_factory):
        super().__init__(connection, cache)
        self._session_factory = session_factory

    async def handle(self, payload: dict):
        from Application.event_handlers.user_registered import UserRegisteredHandler
        from Application.use_cases.register_doctor import RegisterDoctorUseCase
        from infrastructure.repositories import DoctorRepository

        async with self._session_factory() as session:
            async with session.begin():
                doctor_repo = DoctorRepository(session)
                register_use_case = RegisterDoctorUseCase(doctor_repo)
                handler = UserRegisteredHandler(register_use_case)
                await handler.handle(payload)
