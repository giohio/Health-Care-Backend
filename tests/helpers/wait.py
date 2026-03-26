"""
Poll helpers for async event propagation.
RabbitMQ consumers may take 1-3 seconds
to process events. These helpers retry
until condition is met or timeout.
"""

import asyncio
from typing import Any, Callable

import httpx


async def poll_until(
    fn: Callable,
    check: Callable[[Any], bool],
    timeout_seconds: int = 10,
    interval: float = 0.5,
    label: str = "condition",
    **kwargs,
) -> Any:
    """
    Call fn() every interval seconds until
    check(result) is True or timeout is reached.
    Raises AssertionError on timeout.
    """
    legacy_timeout = kwargs.get("timeout")
    if legacy_timeout is not None:
        timeout_seconds = int(legacy_timeout)

    async with asyncio.timeout(timeout_seconds):
        while True:
            result = await fn()
            if check(result):
                return result
            await asyncio.sleep(interval)
    raise AssertionError(f"Timeout waiting for: {label}")


async def wait_for_appointment_status(
    http: httpx.AsyncClient,
    appointment_url: str,
    appointment_id: str,
    expected_status: str,
    token: str,
    timeout_seconds: int = 10,
    **kwargs,
) -> dict:
    """Poll appointment until it reaches expected status."""

    async def fetch():
        r = await http.get(f"{appointment_url}/{appointment_id}", headers={"Authorization": f"Bearer {token}"})
        return r.json()

    return await poll_until(
        fn=fetch,
        check=lambda r: r.get("status") == expected_status,
        timeout_seconds=timeout_seconds,
        timeout=kwargs.get("timeout"),
        label=f"appointment status={expected_status}",
    )


async def wait_for_notification(
    http: httpx.AsyncClient,
    notification_url: str,
    user_token: str,
    notification_type: str,
    contains_text: str,
    timeout_seconds: int = 10,
    **kwargs,
) -> dict:
    """
    Poll notifications until one matches
    type and contains_text in body or title.
    """

    async def fetch():
        r = await http.get(f"{notification_url}/notifications/me", headers={"Authorization": f"Bearer {user_token}"})
        return r.json()

    def check(resp):
        notifs = resp if isinstance(resp, list) else resp.get("notifications", [])
        return any(
            n.get("type") == notification_type
            and (contains_text in n.get("title", "") or contains_text in n.get("body", ""))
            for n in notifs
        )

    return await poll_until(
        fn=fetch,
        check=check,
        timeout_seconds=timeout_seconds,
        timeout=kwargs.get("timeout"),
        label=f"notification type={notification_type} text='{contains_text}'",
    )


async def wait_for_payment_record(
    http: httpx.AsyncClient,
    payment_url: str,
    appointment_id: str,
    token: str,
    timeout_seconds: int = 10,
    **kwargs,
) -> dict:
    """Poll payment endpoint until payment record is ready with txn ref and amount."""

    async def fetch():
        r = await http.get(
            f"{payment_url}/payments/{appointment_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        return {"status_code": r.status_code, "body": r.json()}

    def check(resp):
        if resp.get("status_code") != 200:
            return False
        body = resp.get("body", {})
        return isinstance(body, dict) and bool(body.get("vnpay_txn_ref")) and body.get("amount") is not None

    result = await poll_until(
        fn=fetch,
        check=check,
        timeout_seconds=timeout_seconds,
        timeout=kwargs.get("timeout"),
        label="payment record ready",
    )
    return result["body"]


async def wait_for_payment_status(
    http: httpx.AsyncClient,
    payment_url: str,
    appointment_id: str,
    expected_status: str | list | tuple,
    token: str,
    timeout_seconds: int = 10,
    **kwargs,
) -> dict:
    async def fetch():
        r = await http.get(
            f"{payment_url}/payments/{appointment_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        return r.json()

    def check(resp):
        status = resp.get("status")
        if isinstance(expected_status, (list, tuple)):
            return status in expected_status
        return status == expected_status

    return await poll_until(
        fn=fetch,
        check=check,
        timeout_seconds=timeout_seconds,
        timeout=kwargs.get("timeout"),
        label=f"payment status={expected_status}",
    )
