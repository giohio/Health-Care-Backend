from Domain import (
    User, IUserRepository, EmailValidator, PasswordValidator, IEventPublisher
)
from Domain.entities.user import UserRole


class RegisterService:
    def __init__(self, user_repository: IUserRepository, password_hasher, event_publisher: IEventPublisher):
        self.user_repository = user_repository
        self.password_hasher = password_hasher
        self.event_publisher = event_publisher

        self.email_validator = EmailValidator()
        self.password_validator = PasswordValidator()

    async def execute(
        self,
        email: str,
        password: str,
        role: UserRole = UserRole.PATIENT
    ) -> User:
        is_valid = self.email_validator.is_valid(email)
        if not is_valid:
            raise ValueError("Invalid email format")

        is_valid, errors = self.password_validator.validate(password)
        if not is_valid:
            raise ValueError(errors)

        if await self.user_repository.get_by_email(email):
            raise ValueError("Email already exists")

        hashed_password = self.password_hasher.hash(password)

        user = User(
            email=email,
            hashed_password=hashed_password,
            role=role
        )

        created_user = await self.user_repository.create(user)

        # Publish event
        try:
            await self.event_publisher.publish(
                exchange="user_events",
                routing_key="user.registered",
                message={
                    "user_id": str(created_user.id),
                    "email": created_user.email,
                    "role": created_user.role.value
                }
            )
        except Exception:
            # We log and swallow the exception here in a real app or use transactional outbox
            # For now, we prefer user creation to succeed even if email/notification fails
            pass

        return created_user
