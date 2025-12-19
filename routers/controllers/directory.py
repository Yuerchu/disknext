from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from middleware.auth import AuthRequired
from middleware.dependencies import SessionDep
from models import (
    DirectoryCreateRequest,
    DirectoryResponse,
    Object,
    ObjectResponse,
    ObjectType,
    PolicyResponse,
    User,
    response,
)

directory_router = APIRouter(
    prefix="/directory",
    tags=["directory"]
)

@directory_router.get(
    path="/{path:path}",
    summary="获取目录内容",
)
async def router_directory_get(
        session: SessionDep,
        user: Annotated[User, Depends(AuthRequired)],
        path: str
) -> DirectoryResponse:
    """
    获取目录内容

    路径必须以用户名开头，如 /api/directory/admin 或 /api/directory/admin/docs

    :param session: 数据库会话
    :param user: 当前登录用户
    :param path: 目录路径（必须以用户名开头）
    :return: 目录内容
    """
    # 路径必须以用户名开头
    path = path.strip("/")
    if not path:
        raise HTTPException(status_code=400, detail="路径不能为空，请使用 /{username} 格式")

    path_parts = path.split("/")
    if path_parts[0] != user.username:
        raise HTTPException(status_code=403, detail="无权访问其他用户的目录")

    folder = await Object.get_by_path(session, user.id, "/" + path, user.username)

    if not folder:
        raise HTTPException(status_code=404, detail="目录不存在")

    if not folder.is_folder:
        raise HTTPException(status_code=400, detail="指定路径不是目录")

    children = await Object.get_children(session, user.id, folder.id)
    policy = await folder.awaitable_attrs.policy

    objects = [
        ObjectResponse(
            id=child.id,
            name=child.name,
            path=f"/{child.name}",  # TODO: 完整路径
            thumb=False,
            size=child.size,
            type=ObjectType.FOLDER if child.is_folder else ObjectType.FILE,
            date=child.updated_at,
            create_date=child.created_at,
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


@directory_router.put(
    path="/",
    summary="创建目录",
)
async def router_directory_create(
        session: SessionDep,
        user: Annotated[User, Depends(AuthRequired)],
        request: DirectoryCreateRequest
) -> response.ResponseModel:
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

    if "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail="目录名称不能包含斜杠")

    # 通过 UUID 获取父目录
    parent = await Object.get(session, Object.id == request.parent_id)
    if not parent or parent.owner_id != user.id:
        raise HTTPException(status_code=404, detail="父目录不存在")

    if not parent.is_folder:
        raise HTTPException(status_code=400, detail="父路径不是目录")

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

    return response.ResponseModel(
        data={
            "id": new_folder_id,
            "name": new_folder_name,
            "parent_id": parent_id,
        }
    )
