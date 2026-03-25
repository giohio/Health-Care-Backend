class RetryableError(Exception):
    """
    Lỗi tạm thời, có thể retry.
    VD: network timeout, DB temporarily unavailable.
    Consumer sẽ retry với backoff.
    """


class NonRetryableError(Exception):
    """
    Lỗi logic, không thể retry.
    VD: invalid payload, entity not found.
    Consumer sẽ reject và gửi vào DLQ.
    """
