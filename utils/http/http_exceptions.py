from typing import Any, NoReturn

from fastapi import HTTPException, status

# --- 400 ---

def ensure_request_param(to_check: Any, *args, **kwargs) -> None:
    """
    Ensures a parameter exists. If not, raises a 400 Bad Request.
    This function returns None if the check passes.
    """
    if not to_check:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, *args, **kwargs)

def raise_bad_request(*args, **kwargs) -> NoReturn:
    """Raises an HTTP 400 Bad Request exception."""
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, *args, **kwargs)

def raise_unauthorized(detail: str | None = None, *args, **kwargs) -> NoReturn:
    """Raises an HTTP 401 Unauthorized exception."""
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail, *args, **kwargs)

def raise_insufficient_quota(detail: str | None = None, *args, **kwargs) -> NoReturn:
    """Raises an HTTP 402 Payment Required exception."""
    raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=detail, *args, **kwargs)

def raise_forbidden(detail: str | None = None, *args, **kwargs) -> NoReturn:
    """Raises an HTTP 403 Forbidden exception."""
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail, *args, **kwargs)

def raise_banned(detail: str = "此文件已被管理员封禁，仅允许删除操作", *args, **kwargs) -> NoReturn:
    """Raises an HTTP 403 Forbidden exception for banned objects."""
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail, *args, **kwargs)

def raise_not_found(detail: str | None = None, *args, **kwargs) -> NoReturn:
    """Raises an HTTP 404 Not Found exception."""
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail, *args, **kwargs)

def raise_conflict(*args, **kwargs) -> NoReturn:
    """Raises an HTTP 409 Conflict exception."""
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, *args, **kwargs)

def raise_precondition_required(*args, **kwargs) -> NoReturn:
    """Raises an HTTP 428 Precondition required exception."""
    raise HTTPException(status_code=status.HTTP_428_PRECONDITION_REQUIRED, *args, **kwargs)

def raise_too_many_requests(*args, **kwargs) -> NoReturn:
    """Raises an HTTP 429 Too Many Requests exception."""
    raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, *args, **kwargs)

# --- 500 ---

def raise_internal_error(detail: str = "服务器出现故障，请稍后再试或联系管理员", *args, **kwargs) -> NoReturn:
    """Raises an HTTP 500 Internal Server Error exception."""
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail, *args, **kwargs)

def raise_not_implemented(detail: str = "尚未支持这种方法", *args, **kwargs) -> NoReturn:
    """Raises an HTTP 501 Not Implemented exception."""
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=detail, *args, **kwargs)

def raise_service_unavailable(*args, **kwargs) -> NoReturn:
    """Raises an HTTP 503 Service Unavailable exception."""
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, *args, **kwargs)

def raise_gateway_timeout(*args, **kwargs) -> NoReturn:
    """Raises an HTTP 504 Gateway Timeout exception."""
    raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, *args, **kwargs)
