from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from loguru import logger as l
from sqlmodel import update as sql_update
from sqlmodel_ext import rel, cond

from middleware.dependencies import SessionDep, TableViewRequestDep
from middleware.scope import require_scope
from sqlmodels import (
    Policy, User, ListResponse,
    Entry, EntryType, AdminFileResponse, FileBanRequest, )
from utils import http_exceptions
from utils.http.error_codes import ErrorCode as E
from utils.storage import create_storage_driver

from .deps import set_ban_recursive

admin_file_router = APIRouter(
    prefix="/file",
    tags=["admin", "admin_file"],
)

@admin_file_router.get(
    path='/',
    summary='获取文件列表',
    description='Get file list',
    dependencies=[Depends(require_scope("admin.files:read:all"))],
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
    result = await Entry.get_with_count(
        session, condition, table_view=table_view,
        load=[rel(Entry.owner), rel(Entry.policy)],
    )

    # 构建响应（owner 和 policy 已预加载，直接访问）
    items: list[AdminFileResponse] = []
    for f in result.items:
        items.append(AdminFileResponse.model_validate(
            f, from_attributes=True,
            update={
                'thumb': False,
                'source_enabled': False,
                'owner_email': f.owner.email if f.owner else "unknown",
                'policy_name': f.policy.name if f.policy else "unknown",
            },
        ))

    return ListResponse(items=items, count=result.count)


@admin_file_router.get(
    path='/{file_id}/preview',
    summary='预览文件',
    description='Preview file by ID',
    dependencies=[Depends(require_scope("admin.files:read:all"))],
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

    if not file_obj.type == EntryType.FILE:
        http_exceptions.raise_bad_request(E.FILE_NOT_FILE, "对象不是文件")

    # 获取物理文件
    physical_file = await file_obj.awaitable_attrs.physical_file
    if not physical_file or not physical_file.storage_path:
        http_exceptions.raise_internal_error(E.FILE_STORAGE_PATH_MISSING, "文件存储路径丢失")

    policy = await Policy.get(session, Policy.id == file_obj.policy_id)
    if not policy:
        http_exceptions.raise_internal_error(E.POLICY_NOT_FOUND, "存储策略不存在")

    driver = create_storage_driver(policy)
    if not await driver.exists(physical_file.storage_path):
        http_exceptions.raise_not_found(E.FILE_PHYSICAL_NOT_FOUND, "物理文件不存在")

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
    user: Annotated[User, Depends(require_scope("admin.files:write:all"))],
) -> None:
    """
    封禁或解禁文件/文件夹。封禁后用户无法访问该文件。
    封禁文件夹时会级联封禁所有子对象。

    :param session: 数据库会话
    :param file_id: 文件UUID
    :param request: 封禁请求
    :param user: 当前管理员用户
    :return: 封禁结果
    """
    file_obj = await Entry.get_exist_one(session, file_id)

    count = await set_ban_recursive(session, file_obj, request.ban, user.id, request.reason)

    action = "封禁" if request.ban else "解禁"
    l.info(f"管理员{action}了对象: {file_obj.name}，共影响 {count} 个对象")


@admin_file_router.delete(
    path='/{file_id}',
    summary='删除文件',
    description='Delete file by ID',
    dependencies=[Depends(require_scope("admin.files:delete:all"))],
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

    if not file_obj.type == EntryType.FILE:
        http_exceptions.raise_bad_request(E.FILE_NOT_FILE, "对象不是文件")

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
    stmt = sql_update(User).where(cond(User.id == owner_id)).values(
        storage=max(0, User.storage - file_size)
    )
    _ = await session.exec(stmt)

    # 使用条件删除
    _ = await Entry.delete(session, condition=Entry.id == file_obj.id)

    l.info(f"管理员删除了文件: {file_name}")