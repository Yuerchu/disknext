"""
WOPI 访问令牌生成与验证。

使用 JWT 签名，payload 包含 file_id, user_id, can_write, exp。
TTL 默认 10 小时（WOPI 规范推荐长 TTL）。
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt

from sqlmodels.wopi import WopiAccessTokenPayload
from utils.conf import appmeta

WOPI_TOKEN_TTL = timedelta(hours=10)
"""WOPI 令牌有效期"""


def create_wopi_token(
    file_id: UUID,
    user_id: UUID,
    can_write: bool = False,
) -> tuple[str, int]:
    """
    创建 WOPI 访问令牌。

    :param file_id: 文件UUID
    :param user_id: 用户UUID
    :param can_write: 是否可写
    :return: (token_string, access_token_ttl_ms)
    """
    expire = datetime.now(timezone.utc) + WOPI_TOKEN_TTL
    payload = {
        "jti": str(uuid4()),
        "file_id": str(file_id),
        "user_id": str(user_id),
        "can_write": can_write,
        "exp": expire,
        "type": "wopi",
    }
    token = jwt.encode(payload, appmeta.secret_key, algorithm="HS256")
    # WOPI 规范要求 access_token_ttl 是毫秒级的 UNIX 时间戳
    access_token_ttl = int(expire.timestamp() * 1000)
    return token, access_token_ttl


def verify_wopi_token(token: str) -> WopiAccessTokenPayload | None:
    """
    验证 WOPI 访问令牌并返回 payload。

    :param token: JWT 令牌字符串
    :return: WopiAccessTokenPayload 或 None（验证失败）
    """
    try:
        payload = jwt.decode(token, appmeta.secret_key, algorithms=["HS256"])
        if payload.get("type") != "wopi":
            return None
        return WopiAccessTokenPayload(
            file_id=UUID(payload["file_id"]),
            user_id=UUID(payload["user_id"]),
            can_write=payload.get("can_write", False),
        )
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return None
