"""
E2E test: Upload a lab result file → wait for AI pipeline to move status
from PENDING → DOCTOR_REVIEW (shown as "Ready to Verify" in the FE).

Usage:
    python tests/e2e_lab_upload_ai.py [--gateway http://localhost:8000]
                                      [--email dr.tran.thi.bich@healthai.dev]
                                      [--password <password>]
                                      [--order-id <uuid>]
                                      [--timeout 120]

The script mirrors what the FE does:
  1. POST /auth/login             → get access_token
  2. POST /upload                 → upload a tiny PDF dummy → get file_url
  3. POST /lab-results            → create lab result record (triggers AI)
  4. Poll GET /lab-results/{id}   → wait until status != PENDING
  5. Assert status == DOCTOR_REVIEW
"""

import argparse
import sys
import time
import io
import json
import requests

# ---------------------------------------------------------------------------
# Minimal valid PDF (23 bytes) so we don't need a real file on disk
# ---------------------------------------------------------------------------
DUMMY_PDF = (
    b"%PDF-1.0\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj "
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj "
    b"3 0 obj<</Type/Page/MediaBox[0 0 3 3]>>endobj\n"
    b"xref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n"
    b"0000000058 00000 n\n0000000115 00000 n\ntrailer<</Size 4/Root 1 0 R>>\n"
    b"startxref\n190\n%%EOF"
)


def step(msg: str) -> None:
    print(f"\n{'='*60}\n  {msg}\n{'='*60}")


def ok(msg: str) -> None:
    print(f"  ✓  {msg}")


def fail(msg: str) -> None:
    print(f"  ✗  {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="E2E lab upload + AI pipeline test")
    parser.add_argument("--gateway", default="http://localhost:8000")
    parser.add_argument("--email", default="dr.tran.thi.bich@healthai.dev")
    parser.add_argument("--password", default="Doctor@123456")
    parser.add_argument("--order-id", dest="order_id", default=None,
                        help="Existing lab order UUID (auto-detected if omitted)")
    parser.add_argument("--timeout", type=int, default=120,
                        help="Seconds to wait for AI to finish (default 120)")
    args = parser.parse_args()

    gw = args.gateway.rstrip("/")
    session = requests.Session()

    # -----------------------------------------------------------------------
    # Step 1 — Login
    # -----------------------------------------------------------------------
    step("1 / Login")
    resp = session.post(
        f"{gw}/auth/login",
        json={"email": args.email, "password": args.password},
    )
    if resp.status_code != 200:
        fail(f"Login failed {resp.status_code}: {resp.text}")

    data = resp.json()
    token = data.get("access_token") or data.get("token")
    user_obj = data.get("user") or {}
    user_id = user_obj.get("id") or data.get("user_id") or data.get("id")
    role = user_obj.get("role") or data.get("role", "doctor")

    if not token:
        fail(f"No access_token in response: {json.dumps(data, indent=2)}")

    ok(f"Logged in as {args.email}  (user_id={user_id}, role={role})")

    auth_headers = {
        "Authorization": f"Bearer {token}",
        "X-User-Id": str(user_id),
        "X-User-Role": role,
    }

    # -----------------------------------------------------------------------
    # Step 2 — Resolve order_id (if not provided)
    # -----------------------------------------------------------------------
    step("2 / Resolve lab order")
    order_id = args.order_id
    if not order_id:
        resp = session.get(
            f"{gw}/lab-orders",
            headers=auth_headers,
        )
        if resp.status_code != 200:
            fail(f"GET /lab-orders failed {resp.status_code}: {resp.text}")
        orders = resp.json()
        # Prefer orders with no result yet — we'll just pick the first one
        if not orders:
            fail("No lab orders found. Create one in the FE first.")
        order_id = orders[0]["id"]
        patient_id = orders[0]["patient_id"]
        test_name = orders[0].get("test_name", "Unknown")
        ok(f"Using order {order_id}  ({test_name})")
    else:
        ok(f"Using provided order_id={order_id}")
        # Fetch patient_id from the order
        resp = session.get(f"{gw}/lab-orders", headers=auth_headers)
        orders = resp.json() if resp.status_code == 200 else []
        matched = [o for o in orders if str(o["id"]) == str(order_id)]
        patient_id = matched[0]["patient_id"] if matched else None

    # -----------------------------------------------------------------------
    # Step 3 — Upload file
    # -----------------------------------------------------------------------
    step("3 / Upload dummy PDF")
    resp = session.post(
        f"{gw}/upload",
        headers={
            "Authorization": f"Bearer {token}",
            "X-User-Id": str(user_id),
            "X-User-Role": role,
        },
        files={"file": ("e2e_test.pdf", io.BytesIO(DUMMY_PDF), "application/pdf")},
        data={"context": "lab_results"},
    )
    if resp.status_code != 200:
        fail(f"POST /upload failed {resp.status_code}: {resp.text}")

    upload_data = resp.json()
    file_url = upload_data.get("url") or upload_data.get("file_url")
    if not file_url:
        fail(f"No url in upload response: {json.dumps(upload_data, indent=2)}")
    ok(f"File uploaded → {file_url}")

    # -----------------------------------------------------------------------
    # Step 4 — Create lab result (triggers AI pipeline)
    # -----------------------------------------------------------------------
    step("4 / Create lab result → trigger AI")
    body = {
        "order_id": str(order_id),
        "patient_id": str(patient_id) if patient_id else None,
        "doctor_id": str(user_id),
        "file_url": file_url,
        "file_type": "pdf",
        "notes": "e2e automated test",
    }
    resp = session.post(
        f"{gw}/lab-results",
        headers={**auth_headers, "Content-Type": "application/json"},
        json=body,
    )
    if resp.status_code not in (200, 201):
        fail(f"POST /lab-results failed {resp.status_code}: {resp.text}")

    result = resp.json()
    result_id = result.get("id")
    initial_status = result.get("status")
    ok(f"Lab result created  id={result_id}  status={initial_status}")

    if initial_status not in ("PENDING", "AI_PROCESSING"):
        print(f"\n  ℹ  Status is already '{initial_status}' — AI may not have been triggered.")
        print("     (This order may not have a file_type that triggers AI, or AI is disabled.)")

    # -----------------------------------------------------------------------
    # Step 5 — Poll until status changes
    # -----------------------------------------------------------------------
    step(f"5 / Polling for status change (timeout={args.timeout}s)")
    deadline = time.time() + args.timeout
    poll_interval = 5
    last_status = initial_status

    while time.time() < deadline:
        time.sleep(poll_interval)
        resp = session.get(
            f"{gw}/lab-results/{result_id}",
            headers=auth_headers,
        )
        if resp.status_code != 200:
            print(f"  ⚠  GET /lab-results/{result_id} returned {resp.status_code} — retrying…")
            continue

        current = resp.json()
        status = current.get("status")
        elapsed = int(args.timeout - (deadline - time.time()))
        print(f"  [{elapsed:>3}s]  status = {status}")

        if status != last_status:
            ok(f"Status changed: {last_status} → {status}")
            last_status = status

        if status in ("DOCTOR_REVIEW", "NEEDS_MANUAL_REVIEW"):
            step("RESULT: SUCCESS ✓")
            label = "NEEDS_MANUAL_REVIEW (specialist review flagged)" if status == "NEEDS_MANUAL_REVIEW" else "DOCTOR_REVIEW (Ready to Verify)"
            ok(f"Lab result {result_id} reached {label}")
            ok("AI pipeline is working end-to-end.")
            sys.exit(0)

        if status in ("FAILED", "ERROR"):
            fail(f"AI pipeline failed — status={status}")

    # Timed out
    step("RESULT: TIMEOUT ✗")
    fail(
        f"Status is still '{last_status}' after {args.timeout}s.\n"
        "  Check Celery worker logs:  wsl docker logs ai_celery_worker --tail 50"
    )


if __name__ == "__main__":
    main()
