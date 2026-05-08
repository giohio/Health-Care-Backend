import logging

from Domain.interfaces.email_sender import IEmailSender
from healthai_events.consumer import BaseConsumer

logger = logging.getLogger(__name__)

OTP_EMAIL_SUBJECT = "HealthAI – Xác thực email của bạn"
OTP_EMAIL_BODY = (
    "Xin chào,\n\n"
    "Mã xác thực OTP của bạn là: {otp}\n\n"
    "Mã có hiệu lực trong 10 phút. Vui lòng không chia sẻ mã này với bất kỳ ai.\n\n"
    "Nếu bạn không yêu cầu mã này, hãy bỏ qua email này.\n\n"
    "Trân trọng,\nTeam HealthAI"
)


class UserRegisteredConsumer(BaseConsumer):
    """Sends OTP email after a new patient registers."""

    QUEUE = "notification.user.registered"
    EXCHANGE = "user_events"
    ROUTING_KEY = "user.registered"

    def __init__(self, connection, cache, email_sender: IEmailSender):
        super().__init__(connection, cache)
        self._email_sender = email_sender

    async def handle(self, payload: dict):
        otp = payload.get("otp")
        email = payload.get("email")
        if not otp or not email:
            # Staff registration — no OTP needed
            return

        body = OTP_EMAIL_BODY.format(otp=otp)
        sent = await self._email_sender.send_email(to=email, subject=OTP_EMAIL_SUBJECT, body=body)
        if sent:
            logger.info("OTP email sent to %s", email)
        else:
            logger.warning("OTP email delivery failed for %s", email)


class UserResendOTPConsumer(BaseConsumer):
    """Sends a new OTP email when the user requests a resend."""

    QUEUE = "notification.user.resend_otp"
    EXCHANGE = "user_events"
    ROUTING_KEY = "user.resend_otp"

    def __init__(self, connection, cache, email_sender: IEmailSender):
        super().__init__(connection, cache)
        self._email_sender = email_sender

    async def handle(self, payload: dict):
        otp = payload.get("otp")
        email = payload.get("email")
        if not otp or not email:
            logger.warning("resend_otp event missing otp or email")
            return

        body = OTP_EMAIL_BODY.format(otp=otp)
        sent = await self._email_sender.send_email(to=email, subject=OTP_EMAIL_SUBJECT, body=body)
        if sent:
            logger.info("Resend OTP email sent to %s", email)
        else:
            logger.warning("Resend OTP email delivery failed for %s", email)
