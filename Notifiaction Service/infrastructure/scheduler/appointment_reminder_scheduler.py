import asyncio
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from healthai_cache import CacheClient

logger = logging.getLogger(__name__)


class AppointmentReminderScheduler:
    def __init__(self, session_factory, appointment_client, cache: CacheClient):
        self.session_factory = session_factory
        self.appointment_client = appointment_client
        self.scheduler = AsyncIOScheduler()
        self.cache = cache

    async def start(self):
        self.scheduler.add_job(
            self._check_reminders,
            trigger=IntervalTrigger(minutes=10),
            id="appointment_reminder_check",
            replace_existing=True,
        )
        self.scheduler.start()
        await asyncio.sleep(0)
        logger.info("Appointment reminder scheduler started")

    async def stop(self):
        self.scheduler.shutdown()
        await asyncio.sleep(0)
        logger.info("Appointment reminder scheduler stopped")

    async def _check_reminders(self):
        try:
            now = datetime.now()
            tomorrow = now + timedelta(days=1)

            appointments = await self.appointment_client.get_upcoming_appointments(
                start_time=now, end_time=tomorrow + timedelta(hours=2)
            )

            for appt in appointments:
                from datetime import datetime as dt

                appt_datetime = dt.combine(
                    dt.fromisoformat(appt["appointment_date"]).date(), dt.fromisoformat(appt["start_time"]).time()
                )
                time_until = appt_datetime - now

                if timedelta(hours=23, minutes=30) <= time_until <= timedelta(hours=24, minutes=30):
                    if not appt.get("reminder_24h_sent"):
                        await self._send_reminder(appt, "24h")
                elif timedelta(minutes=50) <= time_until <= timedelta(hours=1, minutes=10):
                    if not appt.get("reminder_1h_sent"):
                        await self._send_reminder(appt, "1h")

        except Exception as e:
            logger.error(f"Error checking reminders: {e}")

    async def _send_reminder(self, appointment: dict, reminder_type: str):
        appt_id = appointment["id"]
        lock_key = f"reminder:{appt_id}:{reminder_type}"

        if await self.cache.exists(lock_key):
            return

        await self.cache.setex(lock_key, 7200, "1")

        async with self.session_factory() as session:
            from infrastructure.repositories.notification_repository import NotificationRepository

            repo = NotificationRepository(session)
            time_str = reminder_type.replace("h", " hour" if reminder_type == "1h" else " hours")
            message = f"Reminder: Your appointment is in {time_str}"
            await repo.create(
                user_id=appointment["patient_id"],
                title="Appointment Reminder",
                message=message,
                notification_type="appointment_reminder",
                related_id=appt_id,
            )
            await session.commit()

        await self.appointment_client.mark_reminder_sent(appt_id, reminder_type)
        logger.info(f"Sent {reminder_type} reminder for appointment {appt_id}")
