from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from middleware.auth import auth_required
from middleware.dependencies import SessionDep
from sqlmodels import (
    DirectoryCreateRequest,
    DirectoryResponse,
    Object,
    ObjectResponse,
    ObjectType,
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
        folder: Object,
) -> DirectoryResponse:
    """
    构建目录响应 DTO

    :param session: 数据库会话
    :param user_id: 用户UUID
    :param folder: 目录对象
    :return: DirectoryResponse
    """
    children = await Object.get_children(session, user_id, folder.id)
    policy = await folder.awaitable_attrs.policy

    objects = [
        ObjectResponse(
            id=child.id,
            name=child.name,
            thumb=False,
            size=child.size,
            type=ObjectType.FOLDER if child.is_folder else ObjectType.FILE,
            created_at=child.created_at,
            updated_at=child.updated_at,
            source_enabled=False,
        )
        for child in children
    ]

    policy_response = PolicyResponse(
        id=policy.id,
        name=policy.name,
        type=policy.type.value,
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
    root = await Object.get_root(session, user.id)
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
        root = await Object.get_root(session, user.id)
        if not root:
            raise HTTPException(status_code=404, detail="根目录不存在")
        return await _get_directory_response(session, user.id, root)

    folder = await Object.get_by_path(session, user.id, "/" + path)

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
)
async def router_directory_create(
        session: SessionDep,
        user: Annotated[User, Depends(auth_required)],
        request: DirectoryCreateRequest
) -> ResponseBase:
    """
    创建目录

    :param session: 数据库会话
    :param user: 当前登录用户
    :param request: 创建请求（包含 parent_id UUID 和 name）
    :return: 创建结果
    """
    # 验证目录名称
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="目录名称不能为空")

    # [TODO] 进一步验证名称合法性
    if "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail="目录名称不能包含斜杠")

    # 通过 UUID 获取父目录
    parent = await Object.get(session, Object.id == request.parent_id)
    if not parent or parent.owner_id != user.id:
        raise HTTPException(status_code=404, detail="父目录不存在")

    if not parent.is_folder:
        raise HTTPException(status_code=400, detail="父路径不是目录")

    if parent.is_banned:
        http_exceptions.raise_banned("目标目录已被封禁，无法执行此操作")

    # 检查是否已存在同名对象
    existing = await Object.get(
        session,
        (Object.owner_id == user.id) &
        (Object.parent_id == parent.id) &
        (Object.name == name)
    )
    if existing:
        raise HTTPException(status_code=409, detail="同名文件或目录已存在")

    policy_id = request.policy_id if request.policy_id else parent.policy_id
    parent_id = parent.id  # 在 save 前保存

    new_folder = Object(
        name=name,
        type=ObjectType.FOLDER,
        owner_id=user.id,
        parent_id=parent_id,
        policy_id=policy_id,
    )
    new_folder_id = new_folder.id  # 在 save 前保存 UUID
    new_folder_name = new_folder.name
    await new_folder.save(session)

    return ResponseBase(
        data={
            "id": new_folder_id,
            "name": new_folder_name,
            "parent_id": parent_id,
        }
    )
