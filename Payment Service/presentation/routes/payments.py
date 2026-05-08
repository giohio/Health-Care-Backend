from datetime import date
from typing import Annotated, List
from urllib.parse import parse_qsl, urlencode
from uuid import UUID

from Application.use_cases.generate_payment_url import GeneratePaymentUrlUseCase
from Application.use_cases.generate_lab_order_payment_url import GenerateLabOrderPaymentUrlUseCase
from Application.use_cases.list_admin_payment_history import ListAdminPaymentHistoryUseCase
from Application.use_cases.handle_vnpay_ipn import ProcessVNPayIPnUseCase
from Application.use_cases.list_patient_payments import ListPatientPaymentsUseCase
from Application.use_cases.list_patient_payment_history import ListPatientPaymentHistoryUseCase
from Application.use_cases.process_vnpay_ipn import GetPaymentUseCase
from Application.use_cases.mark_payment_refunded import MarkPaymentRefundedUseCase
from Application.use_cases.list_lab_fee_configs import ListLabFeeConfigsUseCase
from Application.use_cases.update_lab_fee_config import UpdateLabFeeConfigUseCase
from Domain.value_objects.payment_status import PaymentStatus
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from infrastructure.config import settings
from presentation.dependencies import (
    get_generate_payment_url_use_case,
    get_generate_lab_order_payment_url_use_case,
    get_get_payment_use_case,
    get_list_admin_payment_history_use_case,
    get_list_patient_payment_history_use_case,
    get_list_patient_payments_use_case,
    get_process_vnpay_ipn_use_case,
    get_mark_payment_refunded_use_case,
    get_list_lab_fee_configs_use_case,
    get_update_lab_fee_config_use_case,
)
from presentation.schemas import PaymentHistoryResponseSchema

router = APIRouter(tags=["Payments"])


@router.get(
    "/history",
    response_model=PaymentHistoryResponseSchema,
    summary="List my payment history",
)
async def list_my_payment_history(
    use_case: Annotated[ListPatientPaymentHistoryUseCase, Depends(get_list_patient_payment_history_use_case)],
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    status: PaymentStatus | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    x_user_id: UUID | None = Header(default=None, alias="X-User-Id", include_in_schema=False),
):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="X-User-Id header is missing")
    if from_date and to_date and from_date > to_date:
        raise HTTPException(status_code=400, detail="from_date must be less than or equal to to_date")

    try:
        history = await use_case.execute(
            x_user_id,
            from_date=from_date,
            to_date=to_date,
            status=status,
            page=page,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return PaymentHistoryResponseSchema(status="success", data=history)


@router.get(
    "/admin/history",
    response_model=PaymentHistoryResponseSchema,
    summary="List all payment history for admins",
)
async def list_admin_payment_history(
    use_case: Annotated[ListAdminPaymentHistoryUseCase, Depends(get_list_admin_payment_history_use_case)],
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    status: PaymentStatus | None = Query(default=None),
    patient_id: UUID | None = Query(default=None),
    doctor_id: UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    x_user_role: str | None = Header(default=None, alias="X-User-Role", include_in_schema=False),
):
    if x_user_role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    if from_date and to_date and from_date > to_date:
        raise HTTPException(status_code=400, detail="from_date must be less than or equal to to_date")

    try:
        history = await use_case.execute(
            from_date=from_date,
            to_date=to_date,
            status=status,
            patient_id=patient_id,
            doctor_id=doctor_id,
            page=page,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return PaymentHistoryResponseSchema(status="success", data=history)


@router.get(
    "/my",
    response_model=List[dict],
    summary="List my payments",
)
async def list_my_payments(
    use_case: Annotated[ListPatientPaymentsUseCase, Depends(get_list_patient_payments_use_case)],
    x_user_id: UUID | None = Header(default=None, alias="X-User-Id", include_in_schema=False),
):
    """List all payments belonging to the current logged-in patient (from Kong X-User-Id)."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="X-User-Id header is missing")
    return await use_case.execute(x_user_id)


@router.get(
    "/{appointment_id}",
    response_model=dict,
    responses={404: {"description": "Payment not found"}},
)
async def get_payment(
    appointment_id: UUID,
    use_case: Annotated[GetPaymentUseCase, Depends(get_get_payment_use_case)],
    x_user_id: UUID = Header(alias="X-User-Id", include_in_schema=False),
):
    """Fetch payment record by appointment ID"""
    try:
        payment = await use_case.execute(appointment_id)
        return payment
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/{appointment_id}/pay",
    response_model=dict,
    responses={
        200: {"description": "New payment URL generated"},
        404: {"description": "Payment not found"},
        409: {"description": "Payment already completed or cannot be retried"},
    },
    summary="Generate (or refresh) payment URL",
)
async def generate_payment_url(
    appointment_id: UUID,
    request: Request,
    use_case: Annotated[GeneratePaymentUrlUseCase, Depends(get_generate_payment_url_use_case)],
    x_user_id: UUID = Header(alias="X-User-Id", include_in_schema=False),
):
    """
    Generate a fresh VNPay payment URL for this appointment.
    Call this each time the user wants to pay (or retry after expiry).
    Returns 409 if the payment is already paid, failed, or refunded.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"
    try:
        return await use_case.execute(appointment_id, client_ip=client_ip)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/vnpay/ipn", response_model=dict)
@router.post("/vnpay/ipn", response_model=dict)
async def handle_vnpay_ipn(
    request: Request,
    use_case: Annotated[ProcessVNPayIPnUseCase, Depends(get_process_vnpay_ipn_use_case)],
):
    """
    VNPAY IPN callback endpoint

    Query params:
      vnp_TxnRef, vnp_ResponseCode, vnp_Amount, vnp_TransactionNo,
      vnp_SecureHash, etc.
    """
    params = dict(request.query_params)
    if request.method == "POST":
        try:
            form_data = await request.form()
            params.update({k: str(v) for k, v in form_data.items()})
        except Exception:
            # Fallback when form parser dependency is unavailable.
            raw_body = (await request.body()).decode(errors="ignore")
            if raw_body:
                params.update(dict(parse_qsl(raw_body, keep_blank_values=True)))

    try:
        result = await use_case.execute(params)
        return result
    except Exception as e:
        return {
            "RspCode": "99",
            "Message": str(e),
        }


@router.get("/vnpay/return")
async def handle_vnpay_return(
    request: Request,
    use_case: Annotated[ProcessVNPayIPnUseCase, Depends(get_process_vnpay_ipn_use_case)],
):
    """
    VNPAY return URL (redirect from payment page).
    Also processes the payment update in case IPN didn't reach the server (localhost dev).
    """
    params = dict(request.query_params)

    # Process payment update (same as IPN) — idempotent, safe to run even if IPN already ran
    try:
        await use_case.execute(params)
    except Exception:
        pass  # Best-effort; IPN may have already processed it

    response_code = str(params.get("vnp_ResponseCode", ""))
    transaction_status = str(params.get("vnp_TransactionStatus", ""))
    txn_ref = str(params.get("vnp_TxnRef", ""))

    if response_code == "00" and transaction_status in ("00", ""):
        payment_status = "success"
    elif response_code:
        payment_status = "failed"
    else:
        payment_status = "pending"

    query = urlencode(
        {
            "status": payment_status,
            "txn_ref": txn_ref,
            "response_code": response_code,
            "transaction_status": transaction_status,
        }
    )
    redirect_url = f"{settings.VNPAY_RETURN_URL}?{query}"
    return RedirectResponse(url=redirect_url, status_code=302)


@router.post(
    "/{payment_id}/mark-refunded",
    response_model=dict,
    responses={
        200: {"description": "Payment marked as refunded"},
        403: {"description": "Admin only"},
        404: {"description": "Payment not found"},
        409: {"description": "Payment is not in REFUND_PENDING status"},
    },
    summary="Admin: confirm refund processed",
)
async def admin_mark_refunded(
    payment_id: UUID,
    use_case: Annotated[MarkPaymentRefundedUseCase, Depends(get_mark_payment_refunded_use_case)],
    x_user_role: str | None = Header(default=None, alias="X-User-Role", include_in_schema=False),
):
    """
    Admin endpoint to mark a REFUND_PENDING payment as REFUNDED.
    
    This is called after the admin has manually processed the refund through
    their payment provider (e.g., bank transfer, credit card reversal).
    """
    if x_user_role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    try:
        return await use_case.execute(payment_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get(
    "/config/lab-fees",
    response_model=list[dict],
    summary="Get lab fee configurations",
    tags=["Lab Fee Config"],
)
async def list_lab_fee_configs(
    use_case: Annotated[ListLabFeeConfigsUseCase, Depends(get_list_lab_fee_configs_use_case)],
):
    """
    Get all lab test fee configurations. This endpoint is public and can be accessed
    by doctors to fetch pricing when creating lab orders, and by patients to view fees.
    """
    return await use_case.execute()


@router.put(
    "/config/lab-fees/{test_id}",
    response_model=dict,
    responses={
        200: {"description": "Lab fee updated successfully"},
        403: {"description": "Admin only"},
        404: {"description": "Lab test not found"},
    },
    summary="Update lab fee (admin only)",
    tags=["Lab Fee Config"],
)
async def update_lab_fee_config(
    test_id: str,
    body: dict,
    use_case: Annotated[UpdateLabFeeConfigUseCase, Depends(get_update_lab_fee_config_use_case)],
    x_user_role: str | None = Header(default=None, alias="X-User-Role", include_in_schema=False),
):
    """
    Update the fee for a specific lab test. Admin only endpoint.
    
    Request body: {\"fee\": 150000}
    """
    if x_user_role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    fee = body.get("fee")
    if not isinstance(fee, int) or fee < 0:
        raise HTTPException(status_code=400, detail="Invalid fee value (must be non-negative integer)")

    try:
        return await use_case.execute(test_id, fee)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/lab-orders/{lab_order_id}/pay",
    response_model=dict,
    responses={
        200: {"description": "Payment URL generated successfully"},
        404: {"description": "Payment not found for lab order"},
        400: {"description": "Cannot generate payment URL (payment already paid/refunded)"},
    },
    summary="Generate payment URL for lab order",
    tags=["Lab Order Payment"],
)
async def generate_lab_order_payment_url(
    lab_order_id: str,
    request: Request,
    use_case: Annotated[GenerateLabOrderPaymentUrlUseCase, Depends(get_generate_lab_order_payment_url_use_case)],
):
    """
    Generate a payment URL for a lab order. The patient can use this URL to pay via VNPAY.
    
    If a payment already exists for this lab order:
    - If status is PENDING or EXPIRED, a new URL is generated
    - If status is PAID, REFUND_PENDING, or REFUNDED, an error is returned
    """
    try:
        client_ip = request.client.host if request.client else "127.0.0.1"
        result = await use_case.execute(UUID(lab_order_id), client_ip)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=400, detail=str(e))
