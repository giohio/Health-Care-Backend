import asyncio
import logging
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from Domain.interfaces.email_sender import IEmailSender
from infrastructure.config import settings

logger = logging.getLogger(__name__)


class EmailSender(IEmailSender):
    """SMTP email sender with async wrapper for non-blocking consumers.
    
    Retries transient DNS failures (gaierror) up to 2 times with 1s backoff.
    """

    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.smtp_from = settings.SMTP_FROM

    async def send_email(self, to: str, subject: str, body: str) -> bool:
        if not to:
            return False
        return await asyncio.to_thread(self._send_blocking, to, subject, body)

    def _send_blocking(self, to: str, subject: str, body: str) -> bool:
        message = MIMEMultipart()
        message["From"] = self.smtp_from
        message["To"] = to
        message["Subject"] = subject
        message.attach(MIMEText(body, "plain"))

        max_retries = 2
        for attempt in range(max_retries):
            try:
                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                    server.starttls()
                    server.login(self.smtp_user, self.smtp_password)
                    server.sendmail(self.smtp_from, to, message.as_string())
                logger.info("Email sent successfully to %s", to)
                return True
            except OSError as exc:
                # Transient DNS or network errors (gaierror is OSError subclass)
                if attempt < max_retries - 1:
                    logger.warning("DNS/network error on attempt %d for %s: %s — retrying in 1s", attempt + 1, to, exc)
                    time.sleep(1)
                    continue
                logger.error("Failed to send email to %s after %d attempts: %s", to, max_retries, exc)
                return False
            except Exception as exc:
                logger.error("Failed to send email to %s: %s", to, exc)
                return False
        return False
