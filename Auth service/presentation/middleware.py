import logging
import time

from fastapi import Request
from infrastructure.config import settings
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = (time.time() - start_time) * 1000

        # Log một dòng duy nhất cho gọn
        logger.info(
            f"{request.method} {request.url.path} - " f"Status: {response.status_code} - " f"Time: {process_time:.2f}ms"
        )

        response.headers["X-Process-Time"] = str(process_time)
        return response


class ExceptionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as e:
            logger.exception("Unhandled exception")

            # Trả về lỗi chi tiết nếu là môi trường DEBUG
            error_msg = str(e) if settings.DEBUG else "Internal Server Error"

            return JSONResponse(
                status_code=500, content={"success": False, "message": error_msg, "code": "INTERNAL_SERVER_ERROR"}
            )
