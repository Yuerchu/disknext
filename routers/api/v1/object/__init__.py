from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from middleware.auth import AuthRequired
from middleware.dependencies import SessionDep
from models import Object, ObjectDeleteRequest, ObjectMoveRequest, User
from models.response import ResponseBase

object_router = APIRouter(
    prefix="/object",
    tags=["object"]
)


@object_router.delete(
    path='/',
    summary='删除对象',
    description='删除一个或多个对象（文件或目录）',
)
async def router_object_delete(
    session: SessionDep,
    user: Annotated[User, Depends(AuthRequired)],
    request: ObjectDeleteRequest,
) -> ResponseBase:
    """
    删除对象端点

    :param session: 数据库会话
    :param user: 当前登录用户
    :param request: 删除请求（包含待删除对象的UUID列表）
    :return: 删除结果
    """
    deleted_count = 0

    for obj_id in request.ids:
        obj = await Object.get(session, Object.id == obj_id)
        if obj and obj.owner_id == user.id:
            # TODO: 递归删除子对象（如果是目录）
            # TODO: 更新用户存储空间
            await obj.delete(session)
            deleted_count += 1

    return ResponseBase(
        data={
            "deleted": deleted_count,
            "total": len(request.ids),
        }
    )


@object_router.patch(
    path='/',
    summary='移动对象',
    description='移动一个或多个对象到目标目录',
)
async def router_object_move(
    session: SessionDep,
    user: Annotated[User, Depends(AuthRequired)],
    request: ObjectMoveRequest,
) -> ResponseBase:
    """
    移动对象端点

    :param session: 数据库会话
    :param user: 当前登录用户
    :param request: 移动请求（包含源对象UUID列表和目标目录UUID）
    :return: 移动结果
    """
    # 验证目标目录
    dst = await Object.get(session, Object.id == request.dst_id)
    if not dst or dst.owner_id != user.id:
        raise HTTPException(status_code=404, detail="目标目录不存在")

    if not dst.is_folder:
        raise HTTPException(status_code=400, detail="目标不是有效文件夹")

    moved_count = 0

    for src_id in request.src_ids:
        src = await Object.get(session, Object.id == src_id)
        if not src or src.owner_id != user.id:
            continue

        # 检查是否移动到自身或子目录（防止循环引用）
        if src.id == dst.id:
            continue

        # 检查目标目录下是否存在同名对象
        existing = await Object.get(
            session,
            (Object.owner_id == user.id) &
            (Object.parent_id == dst.id) &
            (Object.name == src.name)
        )
        if existing:
            continue  # 跳过重名对象

        src.parent_id = dst.id
        await src.save(session)
        moved_count += 1

    return ResponseBase(
        data={
            "moved": moved_count,
            "total": len(request.src_ids),
        }
    )

@object_router.post(
    path='/copy',
    summary='复制对象',
    description='Copy an object endpoint.',
    dependencies=[Depends(AuthRequired)]
)
def router_object_copy() -> ResponseBase:
    """
    Copy an object endpoint.
    
    Returns:
        ResponseModel: A model containing the response data for the object copy.
    """
    pass

@object_router.post(
    path='/rename',
    summary='重命名对象',
    description='Rename an object endpoint.',
    dependencies=[Depends(AuthRequired)]
)
def router_object_rename() -> ResponseBase:
    """
    Rename an object endpoint.
    
    Returns:
        ResponseModel: A model containing the response data for the object rename.
    """
    pass

@object_router.get(
    path='/property/{id}',
    summary='获取对象属性',
    description='Get object properties endpoint.',
    dependencies=[Depends(AuthRequired)]
)
def router_object_property(id: str) -> ResponseBase:
    """
    Get object properties endpoint.
    
    Args:
        id (str): The ID of the object to retrieve properties for.
    
    Returns:
        ResponseModel: A model containing the response data for the object properties.
    """
    pass