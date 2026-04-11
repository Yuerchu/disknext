from typing import Annotated
from uuid import UUID

from fastapi import Depends
import jwt

from sqlmodels.user import JWTPayload, User, UserStatus
from utils import JWT
from .dependencies import SessionDep
from utils import http_exceptions
from utils.redis.user_ban_store import UserBanStore


async def jwt_required(
    session: SessionDep,
    token: Annotated[str, Depends(JWT.oauth2_scheme)],
) -> JWTPayload:
    """
    验证 JWT 并返回 claims。

    封禁检查策略（三层）：
    1. JWT 签名校验 + claims.status 快照检查
    2. Redis 黑名单检查（即时封禁生效）
    3. DB 权威源复核（防止 JWT 签发后 DB 状态变更未同步到黑名单的边界情况）
    """
    try:
        payload = jwt.decode(token, JWT.SECRET_KEY, algorithms=["HS256"])
        claims = JWTPayload(
            sub=payload["sub"],
            jti=payload["jti"],
            status=payload["status"],
            group=payload["group"],
        )
    except (jwt.InvalidTokenError, KeyError, ValueError):
        http_exceptions.raise_unauthorized("凭据过期或无效")

    # 1. JWT 内嵌 status 检查
    if claims.status != UserStatus.ACTIVE:
        http_exceptions.raise_forbidden("账户已被禁用")

    # 2. Redis 黑名单即时封禁检查
    if await UserBanStore.is_banned(str(claims.sub)):
        http_exceptions.raise_forbidden("账户已被禁用")

    # 3. DB 权威源复核
    user = await User.get(session, User.id == claims.sub)
    if not user or user.status != UserStatus.ACTIVE:
        http_exceptions.raise_forbidden("账户已被禁用")

    return claims


async def admin_required(
    claims: Annotated[JWTPayload, Depends(jwt_required)],
) -> JWTPayload:
    """
    验证管理员权限（仅读取 JWT claims，不查库）。

    使用方法：
    >>> APIRouter(dependencies=[Depends(admin_required)])
    """
    if not claims.group.admin:
        http_exceptions.raise_forbidden("Admin Required")
    return claims


async def auth_required(
    session: SessionDep,
    claims: Annotated[JWTPayload, Depends(jwt_required)],
) -> User:
    """验证 JWT + 从数据库加载完整 User（含 group 关系）"""
    user = await User.get(session, User.id == claims.sub, load=User.group)
    if not user:
        http_exceptions.raise_unauthorized("用户不存在")
    return user


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
