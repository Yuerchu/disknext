from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import jwt
from fastapi.security import OAuth2PasswordBearer

from sqlmodels.token import AccessTokenBase, RefreshTokenBase
from utils.conf import appmeta

if TYPE_CHECKING:
    from sqlmodels.group import GroupClaims

oauth2_scheme = OAuth2PasswordBearer(
    scheme_name='JWT-Bearer',
    description='用于获取 JWT Bearer 令牌，需要以表单的形式提交',
    tokenUrl="/api/v1/user/session",
    refreshUrl="/api/v1/user/session/refresh",
)


def build_token_payload(
    data: dict,
    is_refresh: bool,
    algorithm: str,
    expires_delta: timedelta | None = None,
) -> tuple[str, datetime]:
    """
    构建令牌。

    :param data: 需要放进 JWT Payload 的字段
    :param is_refresh: 是否为刷新令牌
    :param algorithm: JWT 签名算法
    :param expires_delta: 过期时间
    """

    to_encode = data.copy()

    if is_refresh:
        to_encode.update({"token_type": "refresh"})

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    elif is_refresh:
        expire = datetime.now(timezone.utc) + timedelta(days=30)
    else:
        expire = datetime.now(timezone.utc) + timedelta(hours=1)
    to_encode.update({
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int(expire.timestamp())
    })
    return jwt.encode(to_encode, appmeta.secret_key, algorithm=algorithm), expire


# 访问令牌
def create_access_token(
    sub: UUID,
    jti: UUID,
    *,
    status: str,
    group: "GroupClaims",
    expires_delta: timedelta | None = None,
    algorithm: str = "HS256",
) -> AccessTokenBase:
    """
    生成访问令牌，默认有效期 1 小时。

    :param sub: 令牌的主题，通常是用户 ID。
    :param jti: 令牌的唯一标识符，通常是一个 UUID。
    :param status: 用户状态字符串。
    :param group: 用户组权限快照。
    :param expires_delta: 过期时间, 缺省时为 1 小时。
    :param algorithm: JWT 密钥强度，缺省时为 HS256

    :return: 包含密钥本身和过期时间的 `AccessTokenBase`
    """
    data = {
        "sub": str(sub),
        "jti": str(jti),
        "status": status,
        "group": group.model_dump(mode="json"),
    }

    access_token, expire_at = build_token_payload(
        data,
        False,
        algorithm,
        expires_delta,
    )
    return AccessTokenBase(
        access_token=access_token,
        access_expires=expire_at,
    )


# 刷新令牌
def create_refresh_token(
    sub: UUID,
    jti: UUID,
    expires_delta: timedelta | None = None,
    algorithm: str = "HS256",
    **kwargs,
) -> RefreshTokenBase:
    """
    生成刷新令牌，默认有效期 30 天。

    :param sub: 令牌的主题，通常是用户 ID。
    :param jti: 令牌的唯一标识符，通常是一个 UUID。
    :param expires_delta: 过期时间, 缺省时为 30 天。
    :param algorithm: JWT 密钥强度，缺省时为 HS256
    :param kwargs: 需要放进 JWT Payload 的字段。

    :return: 包含密钥本身和过期时间的 `RefreshTokenBase`
    """

    data = {"sub": str(sub), "jti": str(jti)}

    # 将额外的字段添加到 Payload 中
    for key, value in kwargs.items():
        data[key] = value

    refresh_token, expire_at = build_token_payload(
        data,
        True,
        algorithm,
        expires_delta
    )
    return RefreshTokenBase(
        refresh_token=refresh_token,
        refresh_expires=expire_at,
    )


# ==================== 下载令牌 ====================

DOWNLOAD_TOKEN_TTL = timedelta(hours=1)
"""下载令牌有效期"""


def create_download_token(file_id: UUID, owner_id: UUID) -> str:
    """
    创建一次性文件下载令牌。

    :param file_id: 文件 ID
    :param owner_id: 文件所有者 ID
    :return: JWT 令牌字符串
    """
    payload = {
        "jti": str(uuid4()),
        "file_id": str(file_id),
        "owner_id": str(owner_id),
        "exp": datetime.now(timezone.utc) + DOWNLOAD_TOKEN_TTL,
        "type": "download",
    }
    return jwt.encode(payload, appmeta.secret_key, algorithm="HS256")
