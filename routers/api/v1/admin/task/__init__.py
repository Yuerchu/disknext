from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger as l

from middleware.auth import admin_required
from middleware.dependencies import SessionDep, TableViewRequestDep
from sqlmodels import (
    ResponseBase, ListResponse,
    Task, TaskSummary,
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
    table_view: TableViewRequestDep,
    user_id: UUID | None = None,
    status: str | None = None,
) -> ListResponse[TaskSummary]:
    """
    获取任务列表。

    :param session: 数据库会话
    :param table_view: 分页排序参数依赖
    :param user_id: 按用户筛选
    :param status: 按状态筛选
    :return: 分页任务列表
    """
    conditions = []
    if user_id:
        conditions.append(Task.user_id == user_id)
    if status:
        conditions.append(Task.status == status)

    if conditions:
        condition = conditions[0]
        for c in conditions[1:]:
            condition = condition & c
    else:
        condition = None
    result = await Task.get_with_count(session, condition, table_view=table_view, load=Task.user)

    items: list[TaskSummary] = []
    for t in result.items:
        user = await t.awaitable_attrs.user
        items.append(TaskSummary.from_task(t, user))

    return ListResponse(items=items, count=result.count)


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
        "username": user.email if user else None,
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