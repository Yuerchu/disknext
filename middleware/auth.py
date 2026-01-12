from typing import Annotated
from uuid import UUID

from fastapi import Depends
import jwt

from models.user import User
from utils import JWT
from .dependencies import SessionDep
from utils import http_exceptions

async def auth_required(
    session: SessionDep,
    token: Annotated[str, Depends(JWT.oauth2_scheme)],
) -> User:
    """
    AuthRequired 需要登录
    """
    try:
        payload = jwt.decode(token, JWT.SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("sub")

        if user_id is None:
            http_exceptions.raise_unauthorized("账号或密码错误")

        user_id = UUID(user_id)

        # 从数据库获取用户信息
        user = await User.get(session, User.id == user_id)
        if not user:
            http_exceptions.raise_unauthorized("账号或密码错误")

        return user

    except jwt.InvalidTokenError:
        http_exceptions.raise_unauthorized("账号或密码错误")

async def admin_required(
    user: Annotated[User, Depends(auth_required)],
) -> User:
    """
    验证是否为管理员。

    使用方法：
    >>> APIRouter(dependencies=[Depends(admin_required)])
    """
    group = await user.awaitable_attrs.group
    if group.admin:
        return user
    raise http_exceptions.raise_forbidden("Admin Required")


def verify_download_token(token: str) -> tuple[str, UUID, UUID] | None:
    """
    验证下载令牌并返回 (jti, file_id, owner_id)。

    :param token: JWT 令牌字符串
    :return: (jti, file_id, owner_id) 或 None（验证失败）
    """
    try:
        payload = jwt.decode(token, JWT.SECRET_KEY, algorithms=["HS256"])
        if payload.get("type") != "download":
            http_exceptions.raise_unauthorized("Download token required")
        jti = payload.get("jti")
        if not jti:
            http_exceptions.raise_unauthorized("Download token required")
        return jti, UUID(payload["file_id"]), UUID(payload["owner_id"])
    except jwt.InvalidTokenError:
        http_exceptions.raise_unauthorized("Download token required")