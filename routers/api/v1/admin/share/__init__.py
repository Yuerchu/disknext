from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger as l
from sqlmodel_ext import rel

from middleware.auth import admin_required
from middleware.dependencies import SessionDep, TableViewRequestDep
from sqlmodels import (
    ListResponse,
    Share, AdminShareListItem,
)
from sqlmodel_ext import SQLModelBase


class ShareDetailResponse(SQLModelBase):
    """分享详情响应"""

    id: UUID
    """分享UUID"""

    code: str
    """分享码"""

    views: int
    """浏览次数"""

    downloads: int
    """下载次数"""

    remain_downloads: int | None
    """剩余下载次数"""

    expires: datetime | None
    """过期时间"""

    preview_enabled: bool
    """是否启用预览"""

    score: int
    """评分"""

    has_password: bool
    """是否有密码"""

    user_id: str
    """用户UUID"""

    username: str | None
    """用户名"""

    object: dict | None
    """关联对象信息"""

    created_at: str
    """创建时间"""

admin_share_router = APIRouter(
    prefix='/share',
    tags=['admin', 'admin_share']
)

@admin_share_router.get(
    path='/',
    summary='获取分享列表',
    description='Get share list',
    dependencies=[Depends(admin_required)]
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

    # user 和 entry 已预加载，直接访问
    items: list[AdminShareListItem] = []
    for s in result.items:
        items.append(AdminShareListItem.from_share(s, s.user, s.entry))

    return ListResponse(items=items, count=result.count)


@admin_share_router.get(
    path='/{share_id}',
    summary='获取分享详情',
    description='Get share detail by ID',
    dependencies=[Depends(admin_required)]
)
async def router_admin_get_share(
    session: SessionDep,
    share_id: UUID,
) -> ShareDetailResponse:
    """
    获取分享详情。

    :param session: 数据库会话
    :param share_id: 分享ID
    :return: 分享详情
    """
    share = await Share.get(session, Share.id == share_id, load=rel(Share.entry))
    if not share:
        raise HTTPException(status_code=404, detail="分享不存在")

    obj = await share.awaitable_attrs.object
    user = await share.awaitable_attrs.user

    return ShareDetailResponse(
        id=share.id,
        code=share.code,
        views=share.views,
        downloads=share.downloads,
        remain_downloads=share.remain_downloads,
        expires=share.expires,
        preview_enabled=share.preview_enabled,
        score=share.score,
        has_password=bool(share.password),
        user_id=str(share.user_id),
        username=user.email if user else None,
        object={
            "id": str(obj.id),
            "name": obj.name,
            "type": obj.type.value,
            "size": obj.size,
        } if obj else None,
        created_at=share.created_at.isoformat(),
    )


@admin_share_router.delete(
    path='/{share_id}',
    summary='删除分享',
    description='Delete share by ID',
    dependencies=[Depends(admin_required)],
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

    await Share.delete(session, share)

    l.info(f"管理员删除了分享: {share.code}")