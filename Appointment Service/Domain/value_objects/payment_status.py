from enum import Enum

class PaymentStatus(str, Enum):
    UNPAID = "UNPAID"                 # Chưa trả tiền
    PROCESSING = "PROCESSING"         # Đang xử lý (đang nằm trang VNPay)
    PAID = "PAID"                     # Đã thanh toán thành công
    REFUNDED = "REFUNDED"             # Đã hoàn tiền
