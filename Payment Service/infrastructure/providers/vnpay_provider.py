from Domain.interfaces import IPaymentProvider, PaymentRequest, PaymentResult
from infrastructure.config import settings
from infrastructure.providers.vnpay_helper import generate_payment_url, verify_signature


class VnpayProvider(IPaymentProvider):
    """
    VNPAY implementation of IPaymentProvider.
    """

    async def create_payment_url(self, request: PaymentRequest) -> str:
        return generate_payment_url(
            tmn_code=settings.VNPAY_TMN_CODE,
            hash_secret=settings.VNPAY_HASH_SECRET,
            vnpay_url=settings.VNPAY_URL,
            return_url=request.return_url,
            order_id=str(request.order_id),
            amount=int(request.amount),
            order_desc=request.order_desc,
            client_ip=request.client_ip,
        )

    def verify_callback(self, params: dict) -> PaymentResult:
        if not verify_signature(params, settings.VNPAY_HASH_SECRET):
            return PaymentResult(success=False, provider_ref=None, failure_reason="Invalid signature")

        response_code = params.get("vnp_ResponseCode", "")
        provider_ref = params.get("vnp_TransactionNo")

        if response_code == "00":
            return PaymentResult(success=True, provider_ref=provider_ref)

        return PaymentResult(
            success=False,
            provider_ref=provider_ref,
            failure_reason=f"VNPAY error code: {response_code}",
        )
