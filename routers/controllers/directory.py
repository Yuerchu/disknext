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
        path: str = ""
) -> DirectoryResponse:
    """
    获取目录内容

    :param session: 数据库会话
    :param user: 当前登录用户
    :param path: 目录路径
    :return: 目录内容
    """
    folder = await Object.get_by_path(session, user.id, path or "/")

    if not folder:
        raise HTTPException(status_code=404, detail="目录不存在")

    if not folder.is_folder:
        raise HTTPException(status_code=400, detail="指定路径不是目录")

    children = await Object.get_children(session, user.id, folder.id)
    policy = await folder.awaitable_attrs.policy

    objects = [
        ObjectResponse(
            id=str(child.id),
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

    policy=PolicyResponse(
        id=str(policy.id),
        name=policy.name,
        type=policy.type.value,
        max_size=policy.max_size,
    )

    return DirectoryResponse(
        parent=str(folder.parent_id) if folder.parent_id else None,
        objects=objects,
        policy=policy,
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
    :param request: 创建请求
    :return: 创建结果
    """
    path = request.path.strip()
    if not path or path == "/":
        raise HTTPException(status_code=400, detail="路径不能为空或根目录")

    # 解析路径
    if path.startswith("/"):
        path = path[1:]
    parts = [p for p in path.split("/") if p]

    if not parts:
        raise HTTPException(status_code=400, detail="无效的目录路径")

    new_folder_name = parts[-1]
    parent_path = "/" + "/".join(parts[:-1]) if len(parts) > 1 else "/"

    parent = await Object.get_by_path(session, user.id, parent_path)
    if not parent:
        raise HTTPException(status_code=404, detail="父目录不存在")

    if not parent.is_folder:
        raise HTTPException(status_code=400, detail="父路径不是目录")

    # 检查是否已存在同名对象
    existing = await Object.get(
        session,
        (Object.owner_id == user.id) &
        (Object.parent_id == parent.id) &
        (Object.name == new_folder_name)
    )
    if existing:
        raise HTTPException(status_code=409, detail="同名文件或目录已存在")

    policy_id = request.policy_id if request.policy_id else parent.policy_id

    new_folder = await Object(
        name=new_folder_name,
        type=ObjectType.FOLDER,
        owner_id=user.id,
        parent_id=parent.id,
        policy_id=policy_id,
    ).save(session)

    return response.ResponseModel(
        data={
            "id": new_folder.id,
            "name": new_folder.name,
            "path": f"{parent_path.rstrip('/')}/{new_folder_name}",
        }
    )
