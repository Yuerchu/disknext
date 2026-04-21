from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from middleware.auth import auth_required
from middleware.dependencies import SessionDep
from sqlmodels import (
    DirectoryCreateRequest,
    DirectoryResponse,
    Group,
    File,
    FileResponse,
    EntryType,
    Policy,
    PolicyResponse,
    User,
    ResponseBase,
)
from utils import http_exceptions

directory_router = APIRouter(
    prefix="/directory",
    tags=["directory"]
)


async def _get_directory_response(
        session: AsyncSession,
        user_id: UUID,
        folder: File,
) -> DirectoryResponse:
    """
    构建目录响应 DTO

    :param session: 数据库会话
    :param user_id: 用户UUID
    :param folder: 目录对象
    :return: DirectoryResponse
    """
    children = await File.get_children(session, user_id, folder.id)
    # 直接按 policy_id 查 Policy，避免触发 lazy='raise_on_sql'
    policy = await Policy.get(session, Policy.id == folder.policy_id)
    if not policy:
        raise HTTPException(status_code=500, detail="目录对应的存储策略不存在")

    objects = [
        FileResponse(
            id=child.id,
            name=child.name,
            thumb=False,
            size=child.size,
            type=EntryType.FOLDER if child.is_folder else EntryType.FILE,
            created_at=child.created_at,
            updated_at=child.updated_at,
            source_enabled=False,
        )
        for child in children
    ]

    policy_response = PolicyResponse(
        id=policy.id,
        name=policy.name,
        type=policy.type,
        max_size=policy.max_size,
    )

    return DirectoryResponse(
        id=folder.id,
        parent=folder.parent_id,
        objects=objects,
        policy=policy_response,
    )


@directory_router.get(
    path="/",
    summary="获取根目录内容",
)
async def router_directory_root(
        session: SessionDep,
        user: Annotated[User, Depends(auth_required)],
) -> DirectoryResponse:
    """
    获取当前用户的根目录内容

    :param session: 数据库会话
    :param user: 当前登录用户
    :return: 根目录内容
    """
    root = await File.get_root(session, user.id)
    if not root:
        raise HTTPException(status_code=404, detail="根目录不存在")

    if root.is_banned:
        http_exceptions.raise_banned()

    return await _get_directory_response(session, user.id, root)


@directory_router.get(
    path="/{path:path}",
    summary="获取目录内容",
)
async def router_directory_get(
        session: SessionDep,
        user: Annotated[User, Depends(auth_required)],
        path: str
) -> DirectoryResponse:
    """
    获取目录内容

    路径从用户根目录开始，不包含用户名前缀。
    如 /api/v1/directory/docs 表示根目录下的 docs 目录。

    :param session: 数据库会话
    :param user: 当前登录用户
    :param path: 目录路径（从根目录开始的相对路径）
    :return: 目录内容
    """
    path = path.strip("/")
    if not path:
        # 空路径交给根目录端点处理（理论上不会到达这里）
        root = await File.get_root(session, user.id)
        if not root:
            raise HTTPException(status_code=404, detail="根目录不存在")
        return await _get_directory_response(session, user.id, root)

    folder = await File.get_by_path(session, user.id, "/" + path)

    if not folder:
        raise HTTPException(status_code=404, detail="目录不存在")

    if not folder.is_folder:
        raise HTTPException(status_code=400, detail="指定路径不是目录")

    if folder.is_banned:
        http_exceptions.raise_banned()

    return await _get_directory_response(session, user.id, folder)


@directory_router.post(
    path="/",
    summary="创建目录",
    status_code=204,
)
async def router_directory_create(
        session: SessionDep,
        user: Annotated[User, Depends(auth_required)],
        request: DirectoryCreateRequest
) -> None:
    """
    创建目录

    :param session: 数据库会话
    :param user: 当前登录用户
    :param request: 创建请求（包含 parent_id UUID 和 name）
    :return: 创建结果
    """
    name = File.validate_name(request.name)
    parent = await File.validate_parent(session, request.parent_id, user.id)
    await File.check_name_conflict(session, user.id, parent.id, name)

    policy_id = request.policy_id if request.policy_id else parent.policy_id

    # 校验用户组是否有权使用该策略（仅当用户显式指定 policy_id 时）
    if request.policy_id:
        group = await Group.get(
            session,
            Group.id == user.group_id,
            load=Group.policies,
        )
        if not group or request.policy_id not in {p.id for p in group.policies}:
            raise HTTPException(status_code=403, detail="当前用户组无权使用该存储策略")

    parent_id = parent.id  # 在 save 前保存

    new_folder = File(
        name=name,
        type=EntryType.FOLDER,
        owner_id=user.id,
        parent_id=parent_id,
        policy_id=policy_id,
    )
    new_folder = await new_folder.save(session)
