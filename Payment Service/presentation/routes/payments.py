from typing import Annotated
from uuid import UUID

from Application.use_cases.handle_vnpay_ipn import ProcessVNPayIPnUseCase
from Application.use_cases.process_vnpay_ipn import GetPaymentUseCase
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from presentation.dependencies import get_get_payment_use_case, get_process_vnpay_ipn_use_case

router = APIRouter(tags=["Payments"])


@router.get("/payments/{appointment_id}", response_model=dict)
async def get_payment(
    appointment_id: UUID,
    use_case: Annotated[GetPaymentUseCase, Depends(get_get_payment_use_case)],
    x_user_id: UUID = Header(..., alias="X-User-Id"),
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

    try:
        result = await use_case.execute(params)
        return result
    except Exception as e:
        return {
            "RspCode": "99",
            "Message": str(e),
        }


@router.get("/vnpay/return", response_model=dict)
async def handle_vnpay_return():
    """
    VNPAY return URL (redirect from payment page)
    Status is updated via IPN, not here
    """
    return {
        "message": "Payment processing. Please wait for confirmation.",
    }
