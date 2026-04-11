from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from loguru import logger as l

from middleware.auth import auth_required
from middleware.dependencies import SessionDep
from sqlmodels import (
    Object,
    User,
    WebDAV,
    WebDAVAccountResponse,
    WebDAVCreateRequest,
    WebDAVUpdateRequest,
)
from utils.redis.webdav_auth_cache import WebDAVAuthCache
from utils import http_exceptions
from utils.password.pwd import Password

webdav_router = APIRouter(
    prefix='/webdav',
    tags=["webdav"],
)


def _check_webdav_enabled(user: User) -> None:
    """检查用户组是否启用了 WebDAV 功能"""
    if not user.group.web_dav_enabled:
        http_exceptions.raise_forbidden("WebDAV 功能未启用")


def _to_response(account: WebDAV) -> WebDAVAccountResponse:
    """将 WebDAV 数据库模型转换为响应 DTO"""
    return WebDAVAccountResponse(
        id=account.id,
        name=account.name,
        root=account.root,
        readonly=account.readonly,
        use_proxy=account.use_proxy,
        created_at=str(account.created_at),
        updated_at=str(account.updated_at),
    )


@webdav_router.get(
    path='/accounts',
    summary='获取账号列表',
)
async def list_accounts(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
) -> list[WebDAVAccountResponse]:
    """
    列出当前用户所有 WebDAV 账户

    认证：JWT Bearer Token
    """
    _check_webdav_enabled(user)
    user_id: UUID = user.id

    accounts: list[WebDAV] = await WebDAV.get(
        session,
        WebDAV.user_id == user_id,
        fetch_mode="all",
    )
    return [_to_response(a) for a in accounts]


@webdav_router.post(
    path='/accounts',
    summary='创建账号',
    status_code=201,
)
async def create_account(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    request: WebDAVCreateRequest,
) -> WebDAVAccountResponse:
    """
    创建 WebDAV 账户

    认证：JWT Bearer Token

    错误处理：
    - 403: WebDAV 功能未启用
    - 400: 根目录路径不存在或不是目录
    - 409: 账户名已存在
    """
    _check_webdav_enabled(user)
    user_id: UUID = user.id

    # 验证账户名唯一
    existing = await WebDAV.get(
        session,
        (WebDAV.name == request.name) & (WebDAV.user_id == user_id),
    )
    if existing:
        http_exceptions.raise_conflict("账户名已存在")

    # 验证 root 路径存在且为目录
    root_obj = await Object.get_by_path(session, user_id, request.root)
    if not root_obj or not root_obj.is_folder:
        http_exceptions.raise_bad_request("根目录路径不存在或不是目录")

    # 创建账户
    account = WebDAV(
        name=request.name,
        password=Password.hash(request.password),
        root=request.root,
        readonly=request.readonly,
        use_proxy=request.use_proxy,
        user_id=user_id,
    )
    account = await account.save(session)

    l.info(f"用户 {user_id} 创建 WebDAV 账户: {account.name}")
    return _to_response(account)


@webdav_router.patch(
    path='/accounts/{account_id}',
    summary='更新账号',
)
async def update_account(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    account_id: int,
    request: WebDAVUpdateRequest,
) -> WebDAVAccountResponse:
    """
    更新 WebDAV 账户

    认证：JWT Bearer Token

    错误处理：
    - 403: WebDAV 功能未启用
    - 404: 账户不存在
    - 400: 根目录路径不存在或不是目录
    """
    _check_webdav_enabled(user)
    user_id: UUID = user.id

    account = await WebDAV.get(
        session,
        (WebDAV.id == account_id) & (WebDAV.user_id == user_id),
    )
    if not account:
        http_exceptions.raise_not_found("WebDAV 账户不存在")

    # 验证 root 路径
    if request.root is not None:
        root_obj = await Object.get_by_path(session, user_id, request.root)
        if not root_obj or not root_obj.is_folder:
            http_exceptions.raise_bad_request("根目录路径不存在或不是目录")

    # 密码哈希后原地替换，update() 会通过 model_dump(exclude_unset=True) 只取已设置字段
    is_password_changed = request.password is not None
    if is_password_changed:
        request.password = Password.hash(request.password)

    account = await account.update(session, request)

    # 密码变更时清除认证缓存
    if is_password_changed:
        await WebDAVAuthCache.invalidate_account(user_id, account.name)

    l.info(f"用户 {user_id} 更新 WebDAV 账户: {account.name}")
    return _to_response(account)


@webdav_router.delete(
    path='/accounts/{account_id}',
    summary='删除账号',
    status_code=204,
)
async def delete_account(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    account_id: int,
) -> None:
    """
    删除 WebDAV 账户

    认证：JWT Bearer Token

    错误处理：
    - 403: WebDAV 功能未启用
    - 404: 账户不存在
    """
    _check_webdav_enabled(user)
    user_id: UUID = user.id

    account = await WebDAV.get(
        session,
        (WebDAV.id == account_id) & (WebDAV.user_id == user_id),
    )
    if not account:
        http_exceptions.raise_not_found("WebDAV 账户不存在")

    account_name = account.name
    await WebDAV.delete(session, account)

    # 清除认证缓存
    await WebDAVAuthCache.invalidate_account(user_id, account_name)

    l.info(f"用户 {user_id} 删除 WebDAV 账户: {account_name}")
