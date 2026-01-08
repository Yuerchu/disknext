from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger as l

from middleware.auth import admin_required
from middleware.dependencies import SessionDep
from models import (
    ResponseBase,
    Share, )

admin_share_router = APIRouter(
    prefix='/share',
    tags=['admin', 'admin_share']
)

@admin_share_router.get(
    path='/list',
    summary='获取分享列表',
    description='Get share list',
    dependencies=[Depends(admin_required)]
)
async def router_admin_get_share_list(
    session: SessionDep,
    user_id: UUID | None = None,
    page: int = 1,
    page_size: int = 20,
) -> ResponseBase:
    """
    获取分享列表。

    :param session: 数据库会话
    :param user_id: 按用户筛选
    :param page: 页码
    :param page_size: 每页数量
    :return: 分享列表
    """
    offset = (page - 1) * page_size
    condition = Share.user_id == user_id if user_id else None

    shares = await Share.get(
        session,
        condition,
        fetch_mode="all",
        offset=offset,
        limit=page_size,
        load=Share.user,
    )

    total = await Share.count(session, condition)

    share_list = []
    for s in shares:
        user = await s.awaitable_attrs.user
        obj = await s.awaitable_attrs.object
        share_list.append({
            "id": s.id,
            "code": s.code,
            "views": s.views,
            "downloads": s.downloads,
            "remain_downloads": s.remain_downloads,
            "expires": s.expires.isoformat() if s.expires else None,
            "preview_enabled": s.preview_enabled,
            "score": s.score,
            "user_id": str(s.user_id),
            "username": user.username if user else None,
            "object_name": obj.name if obj else None,
            "created_at": s.created_at.isoformat(),
        })

    return ResponseBase(data={"shares": share_list, "total": total})


@admin_share_router.get(
    path='/{share_id}',
    summary='获取分享详情',
    description='Get share detail by ID',
    dependencies=[Depends(admin_required)]
)
async def router_admin_get_share(
    session: SessionDep,
    share_id: int,
) -> ResponseBase:
    """
    获取分享详情。

    :param session: 数据库会话
    :param share_id: 分享ID
    :return: 分享详情
    """
    share = await Share.get(session, Share.id == share_id, load=Share.object)
    if not share:
        raise HTTPException(status_code=404, detail="分享不存在")

    obj = await share.awaitable_attrs.object
    user = await share.awaitable_attrs.user

    return ResponseBase(data={
        "id": share.id,
        "code": share.code,
        "views": share.views,
        "downloads": share.downloads,
        "remain_downloads": share.remain_downloads,
        "expires": share.expires.isoformat() if share.expires else None,
        "preview_enabled": share.preview_enabled,
        "score": share.score,
        "has_password": bool(share.password),
        "user_id": str(share.user_id),
        "username": user.username if user else None,
        "object": {
            "id": str(obj.id),
            "name": obj.name,
            "type": obj.type.value,
            "size": obj.size,
        } if obj else None,
        "created_at": share.created_at.isoformat(),
    })


@admin_share_router.delete(
    path='/{share_id}',
    summary='删除分享',
    description='Delete share by ID',
    dependencies=[Depends(admin_required)]
)
async def router_admin_delete_share(
    session: SessionDep,
    share_id: int,
) -> ResponseBase:
    """
    删除分享。

    :param session: 数据库会话
    :param share_id: 分享ID
    :return: 删除结果
    """
    share = await Share.get(session, Share.id == share_id)
    if not share:
        raise HTTPException(status_code=404, detail="分享不存在")

    await Share.delete(session, share)

    l.info(f"管理员删除了分享: {share.code}")
    return ResponseBase(data={"deleted": True})