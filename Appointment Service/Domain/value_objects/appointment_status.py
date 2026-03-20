from enum import Enum

class AppointmentStatus(str, Enum):
    PENDING = "PENDING"           # Vừa đặt xong, đang giữ slot (chờ thanh toán nếu có)
    CONFIRMED = "CONFIRMED"       # Đã chốt (thanh toán xong hoặc chọn trả sau)
    IN_PROGRESS = "IN_PROGRESS"   # Đang khám thực tế tại phòng khám
    COMPLETED = "COMPLETED"       # Khám xong
    CANCELLED = "CANCELLED"       # Bị hủy (do timeout 15p hoặc user tự hủy)
    NO_SHOW = "NO_SHOW"           # Khách bùng lịch không đến
