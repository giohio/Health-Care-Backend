import argparse
import asyncio
import base64
import hashlib
import hmac
import json
import os
import random
import statistics
import time
import urllib.parse
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import httpx


@dataclass
class Stage:
    users: int
    duration_seconds: int


@dataclass
class FlowResult:
    success: bool
    reason: str
    latency_ms: float


@dataclass
class Metrics:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    flow_latencies_ms: List[float] = field(default_factory=list)
    flow_success: int = 0
    flow_failed: int = 0
    flow_fail_reasons: Counter = field(default_factory=Counter)
    op_latencies_ms: Dict[str, List[float]] = field(default_factory=lambda: defaultdict(list))
    op_status_counts: Dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))

    async def add_operation(self, op: str, latency_ms: float, status_label: str) -> None:
        async with self.lock:
            self.op_latencies_ms[op].append(latency_ms)
            self.op_status_counts[op][status_label] += 1

    async def add_flow(self, result: FlowResult) -> None:
        async with self.lock:
            if result.success:
                self.flow_success += 1
                self.flow_latencies_ms.append(result.latency_ms)
            else:
                self.flow_failed += 1
                self.flow_fail_reasons[result.reason] += 1


def percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct
    f = int(k)
    c = min(f + 1, len(ordered) - 1)
    if f == c:
        return ordered[f]
    return ordered[f] + (ordered[c] - ordered[f]) * (k - f)


SLOTS_PER_DAY = 27  # 08:00–16:40 in 20-min steps


def get_weekday_dates(n: int) -> List[date]:
    """Return the next n weekdays (Mon–Fri) starting from tomorrow."""
    result: List[date] = []
    candidate = date.today() + timedelta(days=1)
    while len(result) < n:
        if candidate.weekday() < 5:  # Monday to Friday only
            result.append(candidate)
        candidate += timedelta(days=1)
    return result


def slot_time_from_index(slot_index: int) -> str:
    total_minutes = 8 * 60 + slot_index * 20
    hh = total_minutes // 60
    mm = total_minutes % 60
    return f"{hh:02d}:{mm:02d}"


def pick_date_and_slot(worker_id: int, attempt: int, available_dates: List[date]) -> Tuple[str, str]:
    """Deterministically spread workers across dates/slots; shift on retry.

    The total number of unique (date, slot) cells across all dates is
    n_dates × SLOTS_PER_DAY.  We linearise the space and assign each worker
    a starting cell, then step forward by a large prime on each retry so
    successive attempts land on entirely different date+slot combinations.
    """
    n_dates = len(available_dates)
    total_cells = n_dates * SLOTS_PER_DAY
    # Each worker starts at a deterministic cell; step by a large prime to
    # avoid clustering when many workers share the same doctor.
    STEP = 541  # prime > total_cells (20×27=540) so it visits every cell
    cell = (worker_id * 137 + attempt * STEP) % total_cells
    date_idx = cell % n_dates
    slot_idx = cell // n_dates
    return available_dates[date_idx].isoformat(), slot_time_from_index(slot_idx)


def generate_secret(prefix: str) -> str:
    # Keep under common auth max-length constraints while maintaining complexity.
    token = uuid.uuid4().hex[:8]
    return f"{prefix}{token}Aa1!"


def parse_stages(stages_raw: str) -> List[Stage]:
    stages: List[Stage] = []
    for chunk in stages_raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid stage format: {chunk}. Use users:seconds,users:seconds")
        users = int(parts[0])
        seconds = int(parts[1])
        if users <= 0 or seconds <= 0:
            raise ValueError(f"Invalid stage values: {chunk}. users and seconds must be > 0")
        stages.append(Stage(users=users, duration_seconds=seconds))
    if not stages:
        raise ValueError("No stage provided")
    return stages


def jwt_role(access_token: str) -> Optional[str]:
    try:
        payload = access_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8"))
        role = data.get("role")
        return role.lower() if isinstance(role, str) else None
    except Exception:
        return None


async def timed_request(
    client: httpx.AsyncClient,
    metrics: Metrics,
    op_name: str,
    method: str,
    url: str,
    **kwargs,
) -> httpx.Response:
    start = time.perf_counter()
    try:
        response = await client.request(method, url, **kwargs)
        latency_ms = (time.perf_counter() - start) * 1000
        await metrics.add_operation(op_name, latency_ms, str(response.status_code))
        return response
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        await metrics.add_operation(op_name, latency_ms, f"EXC:{type(exc).__name__}")
        raise


async def ensure_admin_token(client: httpx.AsyncClient, base_url: str, admin_email: str, admin_password: str) -> str:
    login = await client.post(
        f"{base_url}/auth/login",
        json={"email": admin_email, "password": admin_password},
    )
    if login.status_code != 200:
        raise RuntimeError(
            "Admin login failed. Ensure ADMIN_EMAIL/ADMIN_PASSWORD exist and seed admin is done. "
            f"status={login.status_code}, body={login.text[:300]}"
        )
    token = login.json().get("access_token")
    if not token:
        raise RuntimeError("Admin login returned no access_token")
    role = jwt_role(token)
    if role != "admin":
        raise RuntimeError(f"Admin token role is {role!r}, expected 'admin'")
    return token


async def create_specialty(client: httpx.AsyncClient, base_url: str, admin_token: str) -> str:
    name = f"LoadTest Specialty {uuid.uuid4().hex[:6]}"
    resp = await client.post(
        f"{base_url}/doctors/specialties",
        json={"name": name},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Create specialty failed: status={resp.status_code}, body={resp.text[:300]}")
    return resp.json()["id"]


async def register_doctor(
    client: httpx.AsyncClient,
    base_url: str,
    admin_token: str,
    specialty_id: str,
    doctor_index: int,
) -> Dict[str, str]:
    email = f"load_doctor_{doctor_index}_{uuid.uuid4().hex[:6]}@healthai.dev"
    password = generate_secret("Dr")

    # Kong may prioritize cookie auth; ensure privileged calls use admin token identity.
    if "access_token" in client.cookies:
        del client.cookies["access_token"]

    reg = await client.post(
        f"{base_url}/auth/admin/register-staff",
        json={"email": email, "password": password, "role": "doctor"},
        headers={"Authorization": f"Bearer {admin_token}", "X-User-Role": "admin"},
    )
    if reg.status_code not in (200, 201):
        raise RuntimeError(f"Register doctor failed: status={reg.status_code}, body={reg.text[:300]}")

    user = reg.json()
    user_id = user["id"]
    full_name = f"Dr Load {doctor_index}"

    provision = await client.post(
        f"{base_url}/doctors/",
        json={"user_id": user_id, "full_name": full_name},
        headers={"Authorization": f"Bearer {admin_token}", "X-User-Role": "admin"},
    )
    if provision.status_code not in (200, 201):
        raise RuntimeError(f"Provision doctor failed: status={provision.status_code}, body={provision.text[:300]}")

    login = await client.post(
        f"{base_url}/auth/login",
        json={"email": email, "password": password},
    )
    if login.status_code != 200:
        raise RuntimeError(f"Doctor login failed: status={login.status_code}, body={login.text[:300]}")
    doctor_token = login.json()["access_token"]

    update = await client.put(
        f"{base_url}/doctors/{user_id}",
        json={
            "user_id": user_id,
            "full_name": full_name,
            "title": "Dr.",
            "specialty_id": specialty_id,
            "experience_years": 8,
        },
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    if update.status_code != 200:
        raise RuntimeError(f"Update doctor profile failed: status={update.status_code}, body={update.text[:300]}")

    schedule_payload = [
        {
            "doctor_id": user_id,
            "day_of_week": day,
            "start_time": "08:00",
            "end_time": "17:00",
            "slot_duration_minutes": 20,
        }
        for day in [0, 1, 2, 3, 4]
    ]
    schedule = await client.put(
        f"{base_url}/doctors/{user_id}/schedule",
        json=schedule_payload,
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    if schedule.status_code != 200:
        raise RuntimeError(f"Set doctor schedule failed: status={schedule.status_code}, body={schedule.text[:300]}")

    auto_confirm = await client.put(
        f"{base_url}/doctors/me/auto-confirm",
        json={"auto_confirm": True, "confirmation_timeout_minutes": 15},
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    if auto_confirm.status_code != 200:
        raise RuntimeError(f"Enable auto-confirm failed: status={auto_confirm.status_code}, body={auto_confirm.text[:300]}")

    return {"user_id": user_id, "access_token": doctor_token, "specialty_id": specialty_id}


def build_vnpay_signature(secret: str, params: Dict[str, str]) -> str:
    filtered = {k: v for k, v in params.items() if k not in ("vnp_SecureHash", "vnp_SecureHashType")}
    query = urllib.parse.urlencode(sorted(filtered.items()))
    return hmac.new(secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha512).hexdigest()


async def wait_for_payment_record(
    client: httpx.AsyncClient,
    metrics: Metrics,
    base_url: str,
    appointment_id: str,
    patient_token: str,
    timeout_seconds: int = 20,
) -> Optional[dict]:
    deadline = time.perf_counter() + timeout_seconds
    while time.perf_counter() < deadline:
        resp = await timed_request(
            client,
            metrics,
            "payment_get",
            "GET",
            f"{base_url}/payments/{appointment_id}",
            headers={"Authorization": f"Bearer {patient_token}"},
        )
        if resp.status_code == 200:
            body = resp.json()
            if body.get("vnpay_txn_ref") and body.get("amount") is not None:
                return body
        await asyncio.sleep(0.4)
    return None


async def wait_for_appointment_confirmed(
    client: httpx.AsyncClient,
    metrics: Metrics,
    base_url: str,
    appointment_id: str,
    patient_token: str,
    timeout_seconds: int = 25,
) -> bool:
    deadline = time.perf_counter() + timeout_seconds
    while time.perf_counter() < deadline:
        resp = await timed_request(
            client,
            metrics,
            "appointment_get",
            "GET",
            f"{base_url}/appointments/{appointment_id}",
            headers={"Authorization": f"Bearer {patient_token}"},
        )
        if resp.status_code == 200:
            status = resp.json().get("status")
            if status == "CONFIRMED":
                return True
        await asyncio.sleep(0.5)
    return False


async def register_patient(
    client: httpx.AsyncClient,
    metrics: Metrics,
    base_url: str,
    worker_id: int,
) -> Tuple[str, str]:
    email = f"load_patient_{worker_id}_{uuid.uuid4().hex[:8]}@healthai.dev"
    password = generate_secret("Pt")

    # Keep flow identity consistent with Authorization header, not stale cookie session.
    if "access_token" in client.cookies:
        del client.cookies["access_token"]

    reg = await timed_request(
        client,
        metrics,
        "auth_register",
        "POST",
        f"{base_url}/auth/register",
        json={"email": email, "password": password},
    )
    if reg.status_code not in (200, 201):
        raise RuntimeError(f"register failed: status={reg.status_code}, body={reg.text[:200]}")

    login = await timed_request(
        client,
        metrics,
        "auth_login",
        "POST",
        f"{base_url}/auth/login",
        json={"email": email, "password": password},
    )
    if login.status_code != 200:
        raise RuntimeError(f"login failed: status={login.status_code}, body={login.text[:200]}")

    token = login.json().get("access_token")
    if not token:
        raise RuntimeError("login missing access_token")

    return login.json().get("user_id", ""), token


async def _attempt_booking(
    client: httpx.AsyncClient,
    metrics: Metrics,
    base_url: str,
    patient_token: str,
    doctor: Dict[str, str],
    worker_id: int,
    available_dates: List[date],
) -> Optional[httpx.Response]:
    """Try to book a slot, retrying on 409/400 conflicts. Returns the last response."""
    MAX_BOOKING_RETRIES = 5
    book: Optional[httpx.Response] = None
    for attempt in range(MAX_BOOKING_RETRIES):
        appt_date, start_time = pick_date_and_slot(worker_id, attempt, available_dates)
        book = await timed_request(
            client,
            metrics,
            "appointment_create",
            "POST",
            f"{base_url}/appointments/",
            json={
                "doctor_id": doctor["user_id"],
                "specialty_id": doctor["specialty_id"],
                "appointment_date": appt_date,
                "start_time": start_time,
                "appointment_type": "general",
            },
            headers={"Authorization": f"Bearer {patient_token}"},
        )
        if book.status_code in (200, 201):
            break
        if book.status_code not in (400, 409):
            # Non-conflict error — report immediately.
            break
        # 409 slot taken → try next date/slot combination
        await asyncio.sleep(0.05 * (attempt + 1))
    return book


async def run_user_flow(
    client: httpx.AsyncClient,
    metrics: Metrics,
    base_url: str,
    patient_token: str,
    doctor_pool: List[Dict[str, str]],
    vnpay_hash_secret: str,
    worker_id: int = 0,
    available_dates: Optional[List[date]] = None,
) -> FlowResult:
    flow_start = time.perf_counter()
    if available_dates is None:
        available_dates = get_weekday_dates(10)
    try:
        # Assign doctor deterministically by worker_id to minimise cross-worker slot collision.
        doctor = doctor_pool[worker_id % len(doctor_pool)]

        book = await _attempt_booking(client, metrics, base_url, patient_token, doctor, worker_id, available_dates)

        if book is None or book.status_code not in (200, 201):
            if book is not None and book.status_code in (400, 409):
                reason = "booking_conflict"
            elif book is not None:
                reason = f"booking_{book.status_code}"
            else:
                reason = "booking_none"
            return FlowResult(success=False, reason=reason, latency_ms=(time.perf_counter() - flow_start) * 1000)

        appointment_id = book.json()["id"]

        payment_record = await wait_for_payment_record(client, metrics, base_url, appointment_id, patient_token)
        if not payment_record:
            return FlowResult(success=False, reason="payment_record_timeout", latency_ms=(time.perf_counter() - flow_start) * 1000)

        params = {
            "vnp_TxnRef": payment_record["vnpay_txn_ref"],
            "vnp_Amount": str(int(payment_record["amount"]) * 100),
            "vnp_ResponseCode": "00",
            "vnp_TransactionNo": f"VNP{int(time.time() * 1000)}",
            "vnp_BankCode": "NCB",
            "vnp_PayDate": "20260331120000",
            "vnp_TransactionStatus": "00",
            "vnp_OrderInfo": f"Load payment {appointment_id}",
        }
        params["vnp_SecureHash"] = build_vnpay_signature(vnpay_hash_secret, params)

        ipn = await timed_request(
            client,
            metrics,
            "payment_ipn",
            "GET",
            f"{base_url}/payments/vnpay/ipn",
            params=params,
        )
        if ipn.status_code != 200:
            return FlowResult(success=False, reason=f"ipn_{ipn.status_code}", latency_ms=(time.perf_counter() - flow_start) * 1000)

        confirmed = await wait_for_appointment_confirmed(client, metrics, base_url, appointment_id, patient_token)
        if not confirmed:
            return FlowResult(success=False, reason="confirm_timeout", latency_ms=(time.perf_counter() - flow_start) * 1000)

        # Optional tail call to emulate dashboard polling by user.
        await timed_request(
            client,
            metrics,
            "payment_my",
            "GET",
            f"{base_url}/payments/my",
            headers={"Authorization": f"Bearer {patient_token}"},
        )

        flow_ms = (time.perf_counter() - flow_start) * 1000
        return FlowResult(success=True, reason="ok", latency_ms=flow_ms)

    except Exception as exc:
        return FlowResult(success=False, reason=f"exception_{type(exc).__name__}", latency_ms=(time.perf_counter() - flow_start) * 1000)


async def worker_loop(
    worker_id: int,
    stop_event: asyncio.Event,
    metrics: Metrics,
    base_url: str,
    doctor_pool: List[Dict[str, str]],
    vnpay_hash_secret: str,
    timeout_seconds: float,
) -> None:
    timeout = httpx.Timeout(timeout_seconds, connect=20.0)
    limits = httpx.Limits(max_connections=200, max_keepalive_connections=100)

    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        _, patient_token = await register_patient(client, metrics, base_url, worker_id)

        available_dates = get_weekday_dates(20)  # pre-compute once per worker
        while not stop_event.is_set():
            result = await run_user_flow(
                client=client,
                metrics=metrics,
                base_url=base_url,
                patient_token=patient_token,
                doctor_pool=doctor_pool,
                vnpay_hash_secret=vnpay_hash_secret,
                worker_id=worker_id,
                available_dates=available_dates,
            )
            await metrics.add_flow(result)


def print_summary(metrics: Metrics, started_at: float, stages: List[Stage]) -> None:
    wall_seconds = max(1.0, time.perf_counter() - started_at)

    success = metrics.flow_success
    failed = metrics.flow_failed
    total = success + failed

    print("\n" + "=" * 80)
    print("PHASE 2 LOAD TEST SUMMARY")
    print("=" * 80)
    print(f"Total flows:       {total}")
    print(f"Successful flows:  {success}")
    print(f"Failed flows:      {failed}")
    print(f"Wall time:         {wall_seconds:.1f}s")
    print(f"Flow throughput:   {success / wall_seconds:.2f} successful flows/s")

    if total > 0:
        print(f"Success ratio:     {(success / total) * 100:.2f}%")

    if metrics.flow_latencies_ms:
        print("\nFlow latency (successful only)")
        print(f"  p50: {percentile(metrics.flow_latencies_ms, 0.50):.1f} ms")
        print(f"  p95: {percentile(metrics.flow_latencies_ms, 0.95):.1f} ms")
        print(f"  p99: {percentile(metrics.flow_latencies_ms, 0.99):.1f} ms")
        print(f"  avg: {statistics.mean(metrics.flow_latencies_ms):.1f} ms")

    if metrics.flow_fail_reasons:
        print("\nTop failure reasons")
        for reason, count in metrics.flow_fail_reasons.most_common(10):
            print(f"  - {reason}: {count}")

    print("\nPer-operation metrics")
    for op in sorted(metrics.op_latencies_ms.keys()):
        latencies = metrics.op_latencies_ms[op]
        statuses = metrics.op_status_counts[op]
        if not latencies:
            continue
        print(
            f"  {op:<20} count={len(latencies):<6} "
            f"p95={percentile(latencies, 0.95):>8.1f}ms "
            f"avg={statistics.mean(latencies):>8.1f}ms "
            f"status={dict(statuses)}"
        )

    print("\nExecuted stages:")
    for idx, stage in enumerate(stages, start=1):
        print(f"  Stage {idx}: users={stage.users}, duration={stage.duration_seconds}s")
    print("=" * 80)


async def run_stage(
    stage: Stage,
    stage_index: int,
    metrics: Metrics,
    base_url: str,
    doctor_pool: List[Dict[str, str]],
    vnpay_hash_secret: str,
    timeout_seconds: float,
    worker_counter_start: int,
) -> int:
    print(f"\n[Stage {stage_index}] users={stage.users}, duration={stage.duration_seconds}s")

    stop_event = asyncio.Event()
    workers: List[asyncio.Task] = []

    for i in range(stage.users):
        worker_id = worker_counter_start + i
        task = asyncio.create_task(
            worker_loop(
                worker_id=worker_id,
                stop_event=stop_event,
                metrics=metrics,
                base_url=base_url,
                doctor_pool=doctor_pool,
                vnpay_hash_secret=vnpay_hash_secret,
                timeout_seconds=timeout_seconds,
            )
        )
        workers.append(task)

    await asyncio.sleep(stage.duration_seconds)
    stop_event.set()

    await asyncio.gather(*workers, return_exceptions=True)

    return worker_counter_start + stage.users


async def bootstrap_doctors(
    base_url: str,
    admin_email: str,
    admin_password: str,
    doctor_count: int,
    timeout_seconds: float,
) -> List[Dict[str, str]]:
    timeout = httpx.Timeout(timeout_seconds, connect=20.0)
    limits = httpx.Limits(max_connections=50, max_keepalive_connections=20)

    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        admin_token = await ensure_admin_token(client, base_url, admin_email, admin_password)
        specialty_id = await create_specialty(client, base_url, admin_token)

        doctors: List[Dict[str, str]] = []
        for idx in range(doctor_count):
            doctor = await register_doctor(client, base_url, admin_token, specialty_id, doctor_index=idx + 1)
            doctors.append(doctor)

        return doctors


async def main_async(args: argparse.Namespace) -> None:
    random.seed(args.seed)

    stages = parse_stages(args.stages)
    vnpay_hash_secret = args.vnpay_hash_secret or os.getenv("VNPAY_HASH_SECRET")
    if not vnpay_hash_secret:
        raise RuntimeError("Missing VNPay hash secret. Set --vnpay-hash-secret or VNPAY_HASH_SECRET env")

    admin_email = args.admin_email or os.getenv("ADMIN_EMAIL") or "admin@healthai.dev"
    admin_password = args.admin_password or os.getenv("ADMIN_PASSWORD")
    if not admin_password:
        raise RuntimeError("Missing admin password. Set --admin-password or ADMIN_PASSWORD env")

    print("Bootstrapping doctors/specialty for load scenario...")
    doctor_pool = await bootstrap_doctors(
        base_url=args.base_url,
        admin_email=admin_email,
        admin_password=admin_password,
        doctor_count=args.doctor_count,
        timeout_seconds=args.timeout,
    )
    print(f"Bootstrap complete: doctors={len(doctor_pool)}")

    metrics = Metrics()
    started_at = time.perf_counter()
    worker_counter = 1

    for idx, stage in enumerate(stages, start=1):
        worker_counter = await run_stage(
            stage=stage,
            stage_index=idx,
            metrics=metrics,
            base_url=args.base_url,
            doctor_pool=doctor_pool,
            vnpay_hash_secret=vnpay_hash_secret,
            timeout_seconds=args.timeout,
            worker_counter_start=worker_counter,
        )

    print_summary(metrics, started_at, stages)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Phase 2 load test: realistic flow through gateway "
            "(Auth -> Appointment -> Payment IPN -> Confirmed)."
        )
    )
    parser.add_argument("--base-url", default="http://localhost:8000", help="Gateway base URL")
    parser.add_argument(
        "--stages",
        default="10:60,25:120,50:120",
        help="Comma-separated stages in users:seconds format, e.g. 10:60,20:60,40:120",
    )
    parser.add_argument("--doctor-count", type=int, default=8, help="Number of doctors to bootstrap")
    parser.add_argument("--admin-email", default=None, help="Admin email for bootstrap")
    parser.add_argument("--admin-password", default=None, help="Admin password for bootstrap")
    parser.add_argument("--vnpay-hash-secret", default=None, help="VNPay hash secret")
    parser.add_argument("--timeout", type=float, default=60.0, help="HTTP timeout seconds")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
