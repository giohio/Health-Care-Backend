from typing import Annotated, List
from urllib.parse import parse_qsl, urlencode
from uuid import UUID

from Application.use_cases.generate_payment_url import GeneratePaymentUrlUseCase
from Application.use_cases.handle_vnpay_ipn import ProcessVNPayIPnUseCase
from Application.use_cases.list_patient_payments import ListPatientPaymentsUseCase
from Application.use_cases.process_vnpay_ipn import GetPaymentUseCase
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import RedirectResponse
from infrastructure.config import settings
from presentation.dependencies import (
    get_generate_payment_url_use_case,
    get_get_payment_use_case,
    get_list_patient_payments_use_case,
    get_process_vnpay_ipn_use_case,
)

router = APIRouter(tags=["Payments"])


@router.get(
    "/my",
    response_model=List[dict],
    summary="List my payments",
)
async def list_my_payments(
    use_case: Annotated[ListPatientPaymentsUseCase, Depends(get_list_patient_payments_use_case)],
    x_user_id: UUID = Header(alias="X-User-Id", include_in_schema=False),
):
    """List all payments belonging to the current logged-in patient (from Kong X-User-Id)."""
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
