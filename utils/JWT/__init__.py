from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from fastapi.security import OAuth2PasswordBearer

from models import AccessTokenBase, RefreshTokenBase

oauth2_scheme = OAuth2PasswordBearer(
    scheme_name='获取 JWT Bearer 令牌',
    description='用于获取 JWT Bearer 令牌，需要以表单的形式提交',
    tokenUrl="/api/v1/user/session",
    refreshUrl="/api/v1/user/session/refresh",
)

SECRET_KEY = ''


async def load_secret_key() -> None:
    """
    从数据库读取 JWT 的密钥。
    """
    # 延迟导入以避免循环依赖
    from models.database import get_session
    from models.setting import Setting

    global SECRET_KEY
    async for session in get_session():
        setting = await Setting.get(
            session,
            (Setting.type == "auth") & (Setting.name == "secret_key")
        )
        if setting:
            SECRET_KEY = setting.value


def build_token_payload(
    data: dict,
    is_refresh: bool,
    algorithm: str,
    expires_delta: timedelta | None = None,
) -> tuple[str, datetime]:
    """构建令牌"""

    to_encode = data.copy()

    if is_refresh:
        to_encode.update({"token_type": "refresh"})

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    elif is_refresh:
        expire = datetime.now(timezone.utc) + timedelta(days=30)
    else:
        expire = datetime.now(timezone.utc) + timedelta(hours=3)
    to_encode.update({
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int(expire.timestamp())
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=algorithm), expire


# 访问令牌
def create_access_token(data: dict, expires_delta: timedelta | None = None,
                        algorithm: str = "HS256") -> AccessTokenBase:
    """
    生成访问令牌，默认有效期 3 小时。

    :param data: 需要放进 JWT Payload 的字段。
    :param expires_delta: 过期时间, 缺省时为 3 小时。
    :param algorithm: JWT 密钥强度，缺省时为 HS256

    :return: 包含密钥本身和过期时间的 `AccessTokenBase`
    """

    access_token, expire_at = build_token_payload(data, False, algorithm, expires_delta)
    return AccessTokenBase(
        access_token=access_token,
        access_expires=expire_at,
    )


# 刷新令牌
def create_refresh_token(data: dict, expires_delta: timedelta | None = None,
                         algorithm: str = "HS256") -> RefreshTokenBase:
    """
    生成刷新令牌，默认有效期 30 天。

    :param data: 需要放进 JWT Payload 的字段。
    :param expires_delta: 过期时间, 缺省时为 30 天。
    :param algorithm: JWT 密钥强度，缺省时为 HS256

    :return: 包含密钥本身和过期时间的 `RefreshTokenBase`
    """

    refresh_token, expire_at = build_token_payload(data, True, algorithm, expires_delta)
    return RefreshTokenBase(
        refresh_token=refresh_token,
        refresh_expires=expire_at,
    )


# ==================== 下载令牌 ====================

DOWNLOAD_TOKEN_TTL = timedelta(hours=1)
"""下载令牌有效期"""


def create_download_token(file_id: UUID, owner_id: UUID) -> str:
    """
    创建文件下载令牌。

    :param file_id: 文件 ID
    :param owner_id: 文件所有者 ID
    :return: JWT 令牌字符串
    """
    payload = {
        "file_id": str(file_id),
        "owner_id": str(owner_id),
        "exp": datetime.now(timezone.utc) + DOWNLOAD_TOKEN_TTL,
        "type": "download",
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")