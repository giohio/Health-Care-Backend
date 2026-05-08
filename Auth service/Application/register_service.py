from Application.verify_email import generate_otp
from Domain import EmailValidator, IEventPublisher, IUserRepository, PasswordValidator, User
from Domain.entities.user import UserRole
from infrastructure.repositories.otp_repository import OTPRepository


class RegisterService:
    def __init__(
        self,
        user_repository: IUserRepository,
        password_hasher,
        event_publisher: IEventPublisher,
        otp_repository: OTPRepository,
    ):
        self.user_repository = user_repository
        self.password_hasher = password_hasher
        self.event_publisher = event_publisher
        self.otp_repository = otp_repository

        self.email_validator = EmailValidator()
        self.password_validator = PasswordValidator()

    async def execute(
        self,
        email: str,
        password: str,
        role: UserRole = UserRole.PATIENT,
        full_name: str | None = None,
    ) -> User:
        is_valid = self.email_validator.is_valid(email)
        if not is_valid:
            raise ValueError("Invalid email format")

        is_valid, errors = self.password_validator.validate(password)
        if not is_valid:
            raise ValueError(errors)

        if await self.user_repository.get_by_email(email):
            raise ValueError("Email already exists")

        hashed_password = await self.password_hasher.hash(password)

        # Staff registered by admin is pre-verified; patients must verify via OTP
        needs_verification = role == UserRole.PATIENT
        user = User(
            email=email,
            hashed_password=hashed_password,
            role=role,
            is_email_verified=not needs_verification,
            full_name=full_name,
        )

        created_user = await self.user_repository.create(user)

        if needs_verification:
            otp = generate_otp()
            await self.otp_repository.save(str(created_user.id), otp)
        else:
            otp = None

        # Publish event
        try:
            payload = {
                "user_id": str(created_user.id),
                "email": created_user.email,
                "role": created_user.role.value,
            }
            if otp:
                payload["otp"] = otp
            await self.event_publisher.publish(
                exchange="user_events",
                routing_key="user.registered",
                message=payload,
            )
        except Exception:
            pass

        return created_user
