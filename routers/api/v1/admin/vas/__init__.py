from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from middleware.auth import admin_required
from middleware.dependencies import SessionDep
from models import (
    ResponseBase,
)

admin_vas_router = APIRouter(
    prefix='/vas',
    tags=['admin', 'admin_vas']
)

@admin_vas_router.get(
    path='/list',
    summary='获取增值服务列表',
    description='Get VAS list (orders and storage packs)',
    dependencies=[Depends(admin_required)]
)
async def router_admin_get_vas_list(
    session: SessionDep,
    user_id: UUID | None = None,
    page: int = 1,
    page_size: int = 20,
) -> ResponseBase:
    """
    获取增值服务列表（订单和存储包）。

    :param session: 数据库会话
    :param user_id: 按用户筛选
    :param page: 页码
    :param page_size: 每页数量
    :return: 增值服务列表
    """
    # TODO: 实现增值服务列表
    # 需要查询 Order 和 StoragePack 模型
    raise HTTPException(status_code=501, detail="增值服务管理暂未实现")


@admin_vas_router.get(
    path='/{vas_id}',
    summary='获取增值服务详情',
    description='Get VAS detail by ID',
    dependencies=[Depends(admin_required)]
)
async def router_admin_get_vas(
    session: SessionDep,
    vas_id: UUID,
) -> ResponseBase:
    """
    获取增值服务详情。

    :param session: 数据库会话
    :param vas_id: 增值服务UUID
    :return: 增值服务详情
    """
    # TODO: 实现增值服务详情
    raise HTTPException(status_code=501, detail="增值服务管理暂未实现")


@admin_vas_router.delete(
    path='/{vas_id}',
    summary='删除增值服务',
    description='Delete VAS by ID',
    dependencies=[Depends(admin_required)]
)
async def router_admin_delete_vas(
    session: SessionDep,
    vas_id: UUID,
) -> ResponseBase:
    """
    删除增值服务。

    :param session: 数据库会话
    :param vas_id: 增值服务UUID
    :return: 删除结果
    """
    # TODO: 实现增值服务删除
    raise HTTPException(status_code=501, detail="增值服务管理暂未实现")