"""
回收站路由

提供回收站管理功能：列出、恢复、永久删除、清空。

路由前缀：/trash
"""
from typing import Annotated

from fastapi import APIRouter, Depends
from loguru import logger as l

from middleware.auth import auth_required
from middleware.dependencies import SessionDep
from sqlmodels import File, User
from sqlmodels.file import TrashDeleteRequest, TrashItemResponse, TrashRestoreRequest

trash_router = APIRouter(
    prefix="/trash",
    tags=["trash"],
)


@trash_router.get(
    path='/',
    summary='列出回收站内容',
    description='获取当前用户回收站中的所有顶层对象。',
)
async def router_trash_list(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
) -> list[TrashItemResponse]:
    """
    列出回收站内容

    认证：需要 JWT token

    返回回收站中被直接删除的顶层对象列表，
    不包含其子对象（子对象在恢复/永久删除时会随顶层对象一起处理）。
    """
    items = await File.get_trash_items(session, user.id)

    return [
        TrashItemResponse(
            id=item.id,
            name=item.name,
            type=item.type,
            size=item.size,
            deleted_at=item.deleted_at,
            original_parent_id=item.deleted_original_parent_id,
        )
        for item in items
    ]


@trash_router.patch(
    path='/restore',
    summary='恢复对象',
    description='从回收站恢复一个或多个对象到原位置。如果原位置不存在则恢复到根目录。',
    status_code=204,
)
async def router_trash_restore(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    request: TrashRestoreRequest,
) -> None:
    """
    从回收站恢复对象

    认证：需要 JWT token

    流程：
    1. 验证对象存在且在回收站中（deleted_at IS NOT NULL）
    2. 检查原父目录是否存在且未删除
    3. 存在 → 恢复到原位置；不存在 → 恢复到根目录
    4. 处理同名冲突（自动重命名）
    5. 清除 deleted_at 和 deleted_original_parent_id
    """
    user_id = user.id
    objects_to_restore: list[File] = []

    for obj_id in request.ids:
        obj = await File.get(
            session,
            (File.id == obj_id) & (File.owner_id == user_id) & (File.deleted_at != None)
        )
        if obj:
            objects_to_restore.append(obj)

    if objects_to_restore:
        restored_count = await File.restore_batch(session, objects_to_restore, user_id)
        l.info(f"用户 {user_id} 从回收站恢复了 {restored_count} 个对象")


@trash_router.delete(
    path='/',
    summary='永久删除对象',
    description='永久删除回收站中的指定对象，包括物理文件和数据库记录。',
    status_code=204,
)
async def router_trash_delete(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    request: TrashDeleteRequest,
) -> None:
    """
    永久删除回收站中的对象

    认证：需要 JWT token

    流程：
    1. 验证对象存在且在回收站中
    2. BFS 收集所有子文件的 PhysicalFile
    3. 处理引用计数，引用为 0 时物理删除文件
    4. 硬删除根 Object（CASCADE 清理子对象）
    5. 更新用户存储配额
    """
    user_id = user.id
    objects_to_delete: list[File] = []

    for obj_id in request.ids:
        obj = await File.get(
            session,
            (File.id == obj_id) & (File.owner_id == user_id) & (File.deleted_at != None)
        )
        if obj:
            objects_to_delete.append(obj)

    if objects_to_delete:
        deleted_count = await File.delete(session, objects_to_delete, cleanup_storage=True)
        l.info(f"用户 {user_id} 永久删除了 {deleted_count} 个对象")


@trash_router.delete(
    path='/empty',
    summary='清空回收站',
    description='永久删除回收站中的所有对象。',
    status_code=204,
)
async def router_trash_empty(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
) -> None:
    """
    清空回收站

    认证：需要 JWT token

    获取回收站中所有顶层对象，逐个执行永久删除。
    """
    user_id = user.id
    trash_items = await File.get_trash_items(session, user_id)

    if trash_items:
        deleted_count = await File.delete(session, trash_items, cleanup_storage=True)
        l.info(f"用户 {user_id} 清空回收站，共删除 {deleted_count} 个对象")
