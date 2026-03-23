import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from Domain.interfaces.email_sender import IEmailSender
from infrastructure.config import settings

logger = logging.getLogger(__name__)


class EmailSender(IEmailSender):
    """SMTP email sender with async wrapper for non-blocking consumers."""

    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.smtp_from = settings.SMTP_FROM

    async def send_email(self, to: str, subject: str, body: str) -> None:
        if not to:
            return
        await asyncio.to_thread(self._send_blocking, to, subject, body)

    def _send_blocking(self, to: str, subject: str, body: str) -> None:
        message = MIMEMultipart()
        message["From"] = self.smtp_from
        message["To"] = to
        message["Subject"] = subject
        message.attach(MIMEText(body, "plain"))

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.smtp_from, to, message.as_string())
            logger.info("Email sent successfully to %s", to)
        except Exception as exc:
            logger.error("Failed to send email to %s: %s", to, exc)
