from typing import Annotated
from urllib.parse import parse_qsl, urlencode
from uuid import UUID

from Application.use_cases.handle_vnpay_ipn import ProcessVNPayIPnUseCase
from Application.use_cases.process_vnpay_ipn import GetPaymentUseCase
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import RedirectResponse
from infrastructure.config import settings
from presentation.dependencies import get_get_payment_use_case, get_process_vnpay_ipn_use_case

router = APIRouter(tags=["Payments"])


@router.get(
    "/payments/{appointment_id}",
    response_model=dict,
    responses={404: {"description": "Payment not found"}},
)
async def get_payment(
    appointment_id: UUID,
    use_case: Annotated[GetPaymentUseCase, Depends(get_get_payment_use_case)],
    x_user_id: Annotated[UUID, Header(alias="X-User-Id")],
):
    """Fetch payment record by appointment ID"""
    try:
        payment = await use_case.execute(appointment_id)
        # Verify patient owns this appointment (would need appointment_repo for proper check)
        # For now, trust Kong has verified auth
        return payment
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


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
async def handle_vnpay_return(request: Request):
    """
    VNPAY return URL (redirect from payment page)
    Status of record is still finalized by IPN callback.
    """
    response_code = str(request.query_params.get("vnp_ResponseCode", ""))
    transaction_status = str(request.query_params.get("vnp_TransactionStatus", ""))
    txn_ref = str(request.query_params.get("vnp_TxnRef", ""))

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
