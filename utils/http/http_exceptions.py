"""
HTTP 异常辅助函数

所有错误抛出统一走本模块，确保响应格式一致::

    {"detail": {"code": "entry.not_found", "message": "对象不存在"}}
"""
from typing import Any, NoReturn

from fastapi import HTTPException, status

from .error_codes import ErrorCode


class AppError(HTTPException):
    """
    带机器可读错误代码的 HTTP 异常

    FastAPI 会将 dict 类型的 detail 原样序列化到 JSON 响应。
    """

    def __init__(
        self,
        status_code: int,
        code: ErrorCode,
        message: str | None = None,
    ) -> None:
        detail: dict[str, str] = {"code": code.value}
        if message is not None:
            detail["message"] = message
        super().__init__(status_code=status_code, detail=detail)


# --- 400 ---

def ensure_request_param(to_check: Any, code: ErrorCode, message: str | None = None) -> None:
    """
    确保参数存在，否则抛出 400 Bad Request。

    检查通过时返回 None。
    """
    if not to_check:
        raise AppError(status_code=status.HTTP_400_BAD_REQUEST, code=code, message=message)


def raise_bad_request(code: ErrorCode, message: str | None = None) -> NoReturn:
    """Raises an HTTP 400 Bad Request exception."""
    raise AppError(status_code=status.HTTP_400_BAD_REQUEST, code=code, message=message)


def raise_unauthorized(code: ErrorCode, message: str | None = None) -> NoReturn:
    """Raises an HTTP 401 Unauthorized exception."""
    raise AppError(status_code=status.HTTP_401_UNAUTHORIZED, code=code, message=message)


def raise_insufficient_quota(
    code: ErrorCode = ErrorCode.FILE_QUOTA_EXCEEDED,
    message: str | None = None,
) -> NoReturn:
    """Raises an HTTP 402 Payment Required exception."""
    raise AppError(status_code=status.HTTP_402_PAYMENT_REQUIRED, code=code, message=message)


def raise_forbidden(code: ErrorCode, message: str | None = None) -> NoReturn:
    """Raises an HTTP 403 Forbidden exception."""
    raise AppError(status_code=status.HTTP_403_FORBIDDEN, code=code, message=message)


def raise_banned(
    code: ErrorCode = ErrorCode.ENTRY_BANNED,
    message: str = "此文件已被管理员封禁，仅允许删除操作",
) -> NoReturn:
    """Raises an HTTP 403 Forbidden exception for banned objects."""
    raise AppError(status_code=status.HTTP_403_FORBIDDEN, code=code, message=message)


def raise_not_found(code: ErrorCode, message: str | None = None) -> NoReturn:
    """Raises an HTTP 404 Not Found exception."""
    raise AppError(status_code=status.HTTP_404_NOT_FOUND, code=code, message=message)


def raise_conflict(code: ErrorCode, message: str | None = None) -> NoReturn:
    """Raises an HTTP 409 Conflict exception."""
    raise AppError(status_code=status.HTTP_409_CONFLICT, code=code, message=message)


def raise_unprocessable_entity(code: ErrorCode, message: str | None = None) -> NoReturn:
    """Raises an HTTP 422 Unprocessable Content exception."""
    raise AppError(status_code=422, code=code, message=message)


def raise_precondition_required(code: ErrorCode, message: str | None = None) -> NoReturn:
    """Raises an HTTP 428 Precondition required exception."""
    raise AppError(status_code=status.HTTP_428_PRECONDITION_REQUIRED, code=code, message=message)


def raise_too_many_requests(code: ErrorCode, message: str | None = None) -> NoReturn:
    """Raises an HTTP 429 Too Many Requests exception."""
    raise AppError(status_code=status.HTTP_429_TOO_MANY_REQUESTS, code=code, message=message)


# --- 500 ---

def raise_internal_error(
    code: ErrorCode = ErrorCode.INTERNAL_ERROR,
    message: str = "服务器出现故障，请稍后再试或联系管理员",
) -> NoReturn:
    """Raises an HTTP 500 Internal Server Error exception."""
    raise AppError(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, code=code, message=message)


def raise_not_implemented(
    code: ErrorCode = ErrorCode.NOT_IMPLEMENTED,
    message: str = "尚未支持这种方法",
) -> NoReturn:
    """Raises an HTTP 501 Not Implemented exception."""
    raise AppError(status_code=status.HTTP_501_NOT_IMPLEMENTED, code=code, message=message)


def raise_bad_gateway(code: ErrorCode, message: str | None = None) -> NoReturn:
    """Raises an HTTP 502 Bad Gateway exception."""
    raise AppError(status_code=status.HTTP_502_BAD_GATEWAY, code=code, message=message)


def raise_service_unavailable(code: ErrorCode, message: str | None = None) -> NoReturn:
    """Raises an HTTP 503 Service Unavailable exception."""
    raise AppError(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, code=code, message=message)


def raise_gateway_timeout(code: ErrorCode, message: str | None = None) -> NoReturn:
    """Raises an HTTP 504 Gateway Timeout exception."""
    raise AppError(status_code=status.HTTP_504_GATEWAY_TIMEOUT, code=code, message=message)
