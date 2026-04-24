from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger as l
from sqlmodel_ext import rel

from middleware.scope import require_scope
from middleware.dependencies import SessionDep, TableViewRequestDep
from sqlmodels import (
    ListResponse,
    Share, AdminShareListItem, AdminShareDetailResponse,
    ShareObjectItem,
)

admin_share_router = APIRouter(
    prefix='/share',
    tags=['admin', 'admin_share']
)

@admin_share_router.get(
    path='/',
    summary='获取分享列表',
    description='Get share list',
    dependencies=[Depends(require_scope("admin.shares:read:all"))]
)
async def router_admin_get_share_list(
    session: SessionDep,
    table_view: TableViewRequestDep,
    user_id: UUID | None = None,
) -> ListResponse[AdminShareListItem]:
    """
    获取分享列表。

    :param session: 数据库会话
    :param table_view: 分页排序参数依赖
    :param user_id: 按用户筛选
    :return: 分页分享列表
    """
    condition = Share.user_id == user_id if user_id else None
    result = await Share.get_with_count(
        session, condition, table_view=table_view,
        load=[rel(Share.user), rel(Share.entry)],
    )

    items: list[AdminShareListItem] = []
    for s in result.items:
        items.append(AdminShareListItem.model_validate(
            s, from_attributes=True,
            update={
                'has_password': s.password is not None,
                'username': s.user.email,
                'object_name': s.entry.name,
            },
        ))

    return ListResponse(items=items, count=result.count)


@admin_share_router.get(
    path='/{share_id}',
    summary='获取分享详情',
    description='Get share detail by ID',
    dependencies=[Depends(require_scope("admin.shares:read:all"))]
)
async def router_admin_get_share(
    session: SessionDep,
    share_id: UUID,
) -> AdminShareDetailResponse:
    """
    获取分享详情。

    :param session: 数据库会话
    :param share_id: 分享ID
    :return: 分享详情
    """
    share = await Share.get(session, Share.id == share_id, load=[rel(Share.entry), rel(Share.user)])
    if not share:
        raise HTTPException(status_code=404, detail="分享不存在")

    return AdminShareDetailResponse.model_validate(share, from_attributes=True, update={
        'username': share.user.email,
        'object': ShareObjectItem.model_validate(share.entry, from_attributes=True),
    })


@admin_share_router.delete(
    path='/{share_id}',
    summary='删除分享',
    description='Delete share by ID',
    dependencies=[Depends(require_scope("admin.shares:delete:all"))],
    status_code=204,
)
async def router_admin_delete_share(
    session: SessionDep,
    share_id: UUID,
) -> None:
    """
    删除分享。

    :param session: 数据库会话
    :param share_id: 分享ID
    :return: 删除结果
    """
    share = await Share.get_exist_one(session, share_id)

    _ = await Share.delete(session, share)

    l.info(f"管理员删除了分享: {share.code}")