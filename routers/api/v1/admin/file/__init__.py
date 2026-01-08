from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from loguru import logger as l
from sqlalchemy import and_

from middleware.auth import admin_required
from middleware.dependencies import SessionDep
from models import (
    Policy, PolicyType, User, ResponseBase,
    Object, ObjectType, )
from models.object import AdminFileResponse, FileBanRequest
from service.storage import LocalStorageService

admin_file_router = APIRouter(
    prefix="/file",
    tags=["admin", "admin_file"],
)

@admin_file_router.get(
    path='/list',
    summary='获取文件列表',
    description='Get file list',
    dependencies=[Depends(admin_required)],
)
async def router_admin_get_file_list(
    session: SessionDep,
    user_id: UUID | None = None,
    is_banned: bool | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> ResponseBase:
    """
    获取系统中的文件列表，支持筛选。

    :param session: 数据库会话
    :param user_id: 按用户筛选
    :param is_banned: 按封禁状态筛选
    :param keyword: 按文件名搜索
    :param page: 页码
    :param page_size: 每页数量
    :return: 文件列表
    """
    offset = (page - 1) * page_size

    # 构建查询条件
    conditions = [Object.type == ObjectType.FILE]
    if user_id:
        conditions.append(Object.owner_id == user_id)
    if is_banned is not None:
        conditions.append(Object.is_banned == is_banned)
    if keyword:
        conditions.append(Object.name.ilike(f"%{keyword}%"))

    combined_condition = and_(*conditions) if len(conditions) > 1 else conditions[0]

    files = await Object.get(
        session,
        combined_condition,
        fetch_mode="all",
        offset=offset,
        limit=page_size,
        load=Object.owner,
    )

    total = await Object.count(session, combined_condition)

    # 构建响应
    file_list = []
    for f in files:
        owner = await f.awaitable_attrs.owner
        policy = await f.awaitable_attrs.policy
        file_list.append(AdminFileResponse(
            id=f.id,
            name=f.name,
            type=f.type,
            size=f.size,
            thumb=False,
            date=f.updated_at,
            create_date=f.created_at,
            source_enabled=False,
            owner_id=f.owner_id,
            owner_username=owner.username if owner else "unknown",
            policy_name=policy.name if policy else "unknown",
            is_banned=f.is_banned,
            banned_at=f.banned_at,
            ban_reason=f.ban_reason,
        ).model_dump())

    return ResponseBase(data={"files": file_list, "total": total})


@admin_file_router.get(
    path='/preview/{file_id}',
    summary='预览文件',
    description='Preview file by ID',
    dependencies=[Depends(admin_required)],
)
async def router_admin_preview_file(
    session: SessionDep,
    file_id: UUID,
) -> FileResponse:
    """
    管理员预览文件内容。

    :param session: 数据库会话
    :param file_id: 文件UUID
    :return: 文件内容
    """
    file_obj = await Object.get(session, Object.id == file_id)
    if not file_obj:
        raise HTTPException(status_code=404, detail="文件不存在")

    if not file_obj.is_file:
        raise HTTPException(status_code=400, detail="对象不是文件")

    # 获取物理文件
    physical_file = await file_obj.awaitable_attrs.physical_file
    if not physical_file or not physical_file.storage_path:
        raise HTTPException(status_code=500, detail="文件存储路径丢失")

    policy = await Policy.get(session, Policy.id == file_obj.policy_id)
    if not policy:
        raise HTTPException(status_code=500, detail="存储策略不存在")

    if policy.type == PolicyType.LOCAL:
        storage_service = LocalStorageService(policy)
        if not await storage_service.file_exists(physical_file.storage_path):
            raise HTTPException(status_code=404, detail="物理文件不存在")

        return FileResponse(
            path=physical_file.storage_path,
            filename=file_obj.name,
        )
    else:
        raise HTTPException(status_code=501, detail="S3 存储暂未实现")


@admin_file_router.patch(
    path='/ban/{file_id}',
    summary='封禁/解禁文件',
    description='Ban the file, user can\'t open, copy, move, download or share this file if administrator ban.',
    dependencies=[Depends(admin_required)],
)
async def router_admin_ban_file(
    session: SessionDep,
    file_id: UUID,
    request: FileBanRequest,
    admin: Annotated[User, Depends(admin_required)],
) -> ResponseBase:
    """
    封禁或解禁文件。封禁后用户无法访问该文件。

    :param session: 数据库会话
    :param file_id: 文件UUID
    :param request: 封禁请求
    :param admin: 当前管理员
    :return: 封禁结果
    """
    file_obj = await Object.get(session, Object.id == file_id)
    if not file_obj:
        raise HTTPException(status_code=404, detail="文件不存在")

    file_obj.is_banned = request.is_banned
    if request.is_banned:
        file_obj.banned_at = datetime.now()
        file_obj.banned_by = admin.id
        file_obj.ban_reason = request.reason
    else:
        file_obj.banned_at = None
        file_obj.banned_by = None
        file_obj.ban_reason = None

    file_obj = await file_obj.save(session)

    action = "封禁" if request.is_banned else "解禁"
    l.info(f"管理员{action}了文件: {file_obj.name}")
    return ResponseBase(data={
        "id": str(file_obj.id),
        "is_banned": file_obj.is_banned,
    })


@admin_file_router.delete(
    path='/{file_id}',
    summary='删除文件',
    description='Delete file by ID',
    dependencies=[Depends(admin_required)],
)
async def router_admin_delete_file(
    session: SessionDep,
    file_id: UUID,
    delete_physical: bool = True,
) -> ResponseBase:
    """
    删除文件。

    :param session: 数据库会话
    :param file_id: 文件UUID
    :param delete_physical: 是否同时删除物理文件
    :return: 删除结果
    """
    file_obj = await Object.get(session, Object.id == file_id)
    if not file_obj:
        raise HTTPException(status_code=404, detail="文件不存在")

    if not file_obj.is_file:
        raise HTTPException(status_code=400, detail="对象不是文件")

    file_name = file_obj.name
    file_size = file_obj.size
    owner_id = file_obj.owner_id

    # 删除物理文件（可选）
    if delete_physical:
        physical_file = await file_obj.awaitable_attrs.physical_file
        if physical_file and physical_file.storage_path:
            policy = await Policy.get(session, Policy.id == file_obj.policy_id)
            if policy and policy.type == PolicyType.LOCAL:
                try:
                    storage_service = LocalStorageService(policy)
                    await storage_service.delete_file(physical_file.storage_path)
                except Exception as e:
                    l.warning(f"删除物理文件失败: {e}")

    # 更新用户存储量
    owner = await User.get(session, User.id == owner_id)
    if owner:
        owner.storage = max(0, owner.storage - file_size)
        await owner.save(session)

    await Object.delete(session, file_obj)

    l.info(f"管理员删除了文件: {file_name}")
    return ResponseBase(data={"deleted": True})