from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from loguru import logger as l
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import update as sql_update

from middleware.auth import admin_required
from middleware.dependencies import SessionDep, TableViewRequestDep
from sqlmodels import (
    JWTPayload, Policy, User, ListResponse,
    Entry, EntryType, AdminFileResponse, FileBanRequest, )
from utils.storage import create_storage_driver

async def _set_ban_recursive(
    session: AsyncSession,
    obj: Entry,
    ban: bool,
    admin_id: UUID,
    reason: str | None,
) -> int:
    """
    递归设置封禁状态，返回受影响对象数量。

    :param session: 数据库会话
    :param obj: 要封禁/解禁的对象
    :param ban: True=封禁, False=解禁
    :param admin_id: 管理员UUID
    :param reason: 封禁原因
    :return: 受影响的对象数量
    """
    # [TODO] 效率太低了
    count = 0

    # 如果是文件夹，先递归处理子对象
    if obj.is_folder:
        children = await Entry.get(
            session,
            Entry.parent_id == obj.id,
            fetch_mode="all",
        )
        for child in children:
            count += await _set_ban_recursive(session, child, ban, admin_id, reason)

    # 设置当前对象
    obj.is_banned = ban
    if ban:
        obj.banned_at = datetime.now()
        obj.banned_by = admin_id
        obj.ban_reason = reason
    else:
        obj.banned_at = None
        obj.banned_by = None
        obj.ban_reason = None

    obj = await obj.save(session)
    count += 1
    return count


admin_file_router = APIRouter(
    prefix="/file",
    tags=["admin", "admin_file"],
)

@admin_file_router.get(
    path='/',
    summary='获取文件列表',
    description='Get file list',
    dependencies=[Depends(admin_required)],
)
async def router_admin_get_file_list(
    session: SessionDep,
    table_view: TableViewRequestDep,
    user_id: UUID | None = None,
    is_banned: bool | None = None,
    keyword: str | None = None,
) -> ListResponse[AdminFileResponse]:
    """
    获取系统中的文件列表，支持筛选。

    :param session: 数据库会话
    :param table_view: 分页排序参数依赖
    :param user_id: 按用户筛选
    :param is_banned: 按封禁状态筛选
    :param keyword: 按文件名搜索
    :return: 分页文件列表
    """
    # 构建查询条件
    conditions = [Entry.type == EntryType.FILE]
    if user_id:
        conditions.append(Entry.owner_id == user_id)
    if is_banned is not None:
        conditions.append(Entry.is_banned == is_banned)
    if keyword:
        conditions.append(Entry.name.ilike(f"%{keyword}%"))

    if len(conditions) > 1:
        condition = conditions[0]
        for c in conditions[1:]:
            condition = condition & c
    else:
        condition = conditions[0]
    result = await Entry.get_with_count(session, condition, table_view=table_view, load=Entry.owner)

    # 构建响应
    items: list[AdminFileResponse] = []
    for f in result.items:
        owner = await f.awaitable_attrs.owner
        policy = await f.awaitable_attrs.policy
        items.append(AdminFileResponse.from_object(f, owner, policy))

    return ListResponse(items=items, count=result.count)


@admin_file_router.get(
    path='/{file_id}/preview',
    summary='预览文件',
    description='Preview file by ID',
    dependencies=[Depends(admin_required)],
)
async def router_admin_preview_file(
    session: SessionDep,
    file_id: UUID,
) -> Response:
    """
    管理员预览文件内容。

    :param session: 数据库会话
    :param file_id: 文件UUID
    :return: 文件内容
    """
    file_obj = await Entry.get_exist_one(session, file_id)

    if not file_obj.is_file:
        raise HTTPException(status_code=400, detail="对象不是文件")

    # 获取物理文件
    physical_file = await file_obj.awaitable_attrs.physical_file
    if not physical_file or not physical_file.storage_path:
        raise HTTPException(status_code=500, detail="文件存储路径丢失")

    policy = await Policy.get(session, Policy.id == file_obj.policy_id)
    if not policy:
        raise HTTPException(status_code=500, detail="存储策略不存在")

    driver = create_storage_driver(policy)
    if not await driver.exists(physical_file.storage_path):
        raise HTTPException(status_code=404, detail="物理文件不存在")

    return (await driver.get_download_result(physical_file.storage_path, file_obj.name)).to_response()


@admin_file_router.patch(
    path='/{file_id}',
    summary='封禁/解禁文件',
    description='Ban the file, user can\'t open, copy, move, download or share this file if administrator ban.',
    status_code=204,
)
async def router_admin_ban_file(
    session: SessionDep,
    file_id: UUID,
    request: FileBanRequest,
    claims: Annotated[JWTPayload, Depends(admin_required)],
) -> None:
    """
    封禁或解禁文件/文件夹。封禁后用户无法访问该文件。
    封禁文件夹时会级联封禁所有子对象。

    :param session: 数据库会话
    :param file_id: 文件UUID
    :param request: 封禁请求
    :param claims: 当前管理员 JWT claims
    :return: 封禁结果
    """
    file_obj = await Entry.get_exist_one(session, file_id)

    count = await _set_ban_recursive(session, file_obj, request.ban, claims.sub, request.reason)

    action = "封禁" if request.ban else "解禁"
    l.info(f"管理员{action}了对象: {file_obj.name}，共影响 {count} 个对象")


@admin_file_router.delete(
    path='/{file_id}',
    summary='删除文件',
    description='Delete file by ID',
    dependencies=[Depends(admin_required)],
    status_code=204,
)
async def router_admin_delete_file(
    session: SessionDep,
    file_id: UUID,
    delete_physical: bool = True,
) -> None:
    """
    删除文件。

    :param session: 数据库会话
    :param file_id: 文件UUID
    :param delete_physical: 是否同时删除物理文件
    :return: 删除结果
    """
    file_obj = await Entry.get_exist_one(session, file_id)

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
            if policy:
                try:
                    driver = create_storage_driver(policy)
                    await driver.delete(physical_file.storage_path)
                except Exception as e:
                    l.warning(f"删除物理文件失败: {e}")

    # 更新用户存储量（使用 SQL UPDATE 直接更新，无需加载实例）
    stmt = sql_update(User).where(User.id == owner_id).values(
        storage=max(0, User.storage - file_size)
    )
    await session.exec(stmt)

    # 使用条件删除
    await Entry.delete(session, condition=Entry.id == file_obj.id)

    l.info(f"管理员删除了文件: {file_name}")