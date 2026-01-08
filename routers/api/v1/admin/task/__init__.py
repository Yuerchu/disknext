from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger as l
from sqlalchemy import and_

from middleware.auth import admin_required
from middleware.dependencies import SessionDep
from models import (
    ResponseBase,
    Task,
)

admin_task_router = APIRouter(
    prefix='/task',
    tags=['admin', 'admin_task']
)

@admin_task_router.get(
    path='/list',
    summary='获取任务列表',
    description='Get task list',
    dependencies=[Depends(admin_required)]
)
async def router_admin_get_task_list(
    session: SessionDep,
    user_id: UUID | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> ResponseBase:
    """
    获取任务列表。

    :param session: 数据库会话
    :param user_id: 按用户筛选
    :param status: 按状态筛选
    :param page: 页码
    :param page_size: 每页数量
    :return: 任务列表
    """
    offset = (page - 1) * page_size

    conditions = []
    if user_id:
        conditions.append(Task.user_id == user_id)
    if status:
        conditions.append(Task.status == status)

    condition = and_(*conditions) if conditions else None

    tasks = await Task.get(
        session,
        condition,
        fetch_mode="all",
        offset=offset,
        limit=page_size,
        load=Task.user,
    )

    total = await Task.count(session, condition)

    task_list = []
    for t in tasks:
        user = await t.awaitable_attrs.user
        task_list.append({
            "id": t.id,
            "status": t.status,
            "type": t.type,
            "progress": t.progress,
            "error": t.error,
            "user_id": str(t.user_id),
            "username": user.username if user else None,
            "created_at": t.created_at.isoformat(),
            "updated_at": t.updated_at.isoformat(),
        })

    return ResponseBase(data={"tasks": task_list, "total": total})


@admin_task_router.get(
    path='/{task_id}',
    summary='获取任务详情',
    description='Get task detail by ID',
    dependencies=[Depends(admin_required)]
)
async def router_admin_get_task(
    session: SessionDep,
    task_id: int,
) -> ResponseBase:
    """
    获取任务详情。

    :param session: 数据库会话
    :param task_id: 任务ID
    :return: 任务详情
    """
    task = await Task.get(session, Task.id == task_id, load=Task.props)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    user = await task.awaitable_attrs.user
    props = await task.awaitable_attrs.props

    return ResponseBase(data={
        "id": task.id,
        "status": task.status,
        "type": task.type,
        "progress": task.progress,
        "error": task.error,
        "user_id": str(task.user_id),
        "username": user.username if user else None,
        "props": props.model_dump() if props else None,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    })


@admin_task_router.delete(
    path='/{task_id}',
    summary='删除任务',
    description='Delete task by ID',
    dependencies=[Depends(admin_required)]
)
async def router_admin_delete_task(
    session: SessionDep,
    task_id: int,
) -> ResponseBase:
    """
    删除任务。

    :param session: 数据库会话
    :param task_id: 任务ID
    :return: 删除结果
    """
    task = await Task.get(session, Task.id == task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    await Task.delete(session, task)

    l.info(f"管理员删除了任务: {task_id}")
    return ResponseBase(data={"deleted": True})