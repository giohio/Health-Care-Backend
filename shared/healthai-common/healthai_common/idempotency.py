import json
from functools import wraps

from fastapi import Request
from fastapi.responses import JSONResponse
from healthai_cache import CacheClient


def idempotent(ttl: int = 86400):
    """
    Decorator cho FastAPI endpoint.
    Tự động check + store idempotency.

    Chỉ hoạt động với POST/PATCH/PUT.
    GET requests bỏ qua.

    Header bắt buộc: Idempotency-Key: <uuid>
    Nếu thiếu header → xử lý bình thường (không cache).

    Usage:
        @router.post("/appointments")
        @idempotent(ttl=86400)
        async def create_appointment(
            request: Request,
            body: CreateAppointmentRequest,
            cache: CacheClient = Depends(get_cache)
        ):
            ...

    QUAN TRỌNG: request và cache phải là parameters
    của function. Decorator sẽ inject vào tự động.
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            if request.method not in ("POST", "PUT", "PATCH"):
                return await func(request, *args, **kwargs)

            idem_key = request.headers.get("Idempotency-Key")
            if not idem_key:
                return await func(request, *args, **kwargs)

            # Lấy cache từ app state hoặc từ kwargs
            cache: CacheClient = getattr(request.app.state, "cache", None) or kwargs.get("cache")
            if not cache:
                return await func(request, *args, **kwargs)

            # Check đã xử lý chưa
            cached = await cache.idempotency.get(idem_key)
            if cached:
                return JSONResponse(
                    content=cached["body"], status_code=cached["status_code"], headers={"X-Idempotent-Replayed": "true"}
                )

            # Xử lý bình thường
            response = await func(request, *args, **kwargs)

            # Store response nếu thành công
            if hasattr(response, "status_code"):
                try:
                    body = json.loads(response.body)
                except Exception:
                    body = {}
                await cache.idempotency.store(idem_key, response.status_code, body, ttl=ttl)

            return response

        return wrapper

    return decorator
