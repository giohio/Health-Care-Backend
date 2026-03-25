from datetime import date, datetime, time, timedelta, timezone


def add_minutes(base_time: time, minutes: int) -> time:
    dt = datetime.combine(date.today(), base_time)
    return (dt + timedelta(minutes=minutes)).time()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
