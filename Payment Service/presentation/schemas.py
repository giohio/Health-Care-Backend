from pydantic import BaseModel, ConfigDict


class PaymentHistoryItemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    appointment_id: str
    status: str
    appointment_status: str
    amount: int
    currency: str
    payment_url: str | None = None
    vnpay_txn_ref: str | None = None
    paid_at: str | None = None
    created_at: str | None = None
    patient_id: str | None = None
    doctor_id: str | None = None


class PaymentHistoryPageSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[PaymentHistoryItemSchema]
    total: int
    page: int
    limit: int
    total_pages: int


class PaymentHistoryResponseSchema(BaseModel):
    status: str
    data: PaymentHistoryPageSchema