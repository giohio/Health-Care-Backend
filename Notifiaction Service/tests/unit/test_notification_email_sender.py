import asyncio

import pytest
from infrastructure.email.email_sender import EmailSender


@pytest.mark.asyncio
async def test_send_email_no_recipient_returns_early(monkeypatch):
    called = {"to_thread": 0}

    async def fake_to_thread(*_args, **_kwargs):
        await asyncio.sleep(0)
        called["to_thread"] += 1

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

    sender = EmailSender()
    await sender.send_email("", "sub", "body")

    assert called["to_thread"] == 0


def test_send_blocking_success(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port):
            calls.append(("init", host, port))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def starttls(self):
            calls.append(("starttls",))

        def login(self, user, pwd):
            calls.append(("login", user, pwd))

        def sendmail(self, frm, to, msg):
            calls.append(("sendmail", frm, to, bool(msg)))

    import infrastructure.email.email_sender as module

    monkeypatch.setattr(module.smtplib, "SMTP", FakeSMTP)

    sender = EmailSender()
    sender._send_blocking("to@example.com", "Subject", "Body")

    assert any(c[0] == "sendmail" for c in calls)


def test_send_blocking_handles_smtp_error(monkeypatch):
    class BadSMTP:
        def __init__(self, *_args):
            # Intentionally empty for the SMTP stub used by this test.
            self._unused = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def starttls(self):
            raise RuntimeError("smtp error")

    import infrastructure.email.email_sender as module

    monkeypatch.setattr(module.smtplib, "SMTP", BadSMTP)

    sender = EmailSender()
    sender._send_blocking("to@example.com", "Subject", "Body")
