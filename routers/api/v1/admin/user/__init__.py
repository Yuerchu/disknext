from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger as l
from sqlalchemy import func

from middleware.auth import admin_required
from middleware.dependencies import SessionDep, TableViewRequestDep, UserFilterParamsDep
from models import (
    User, ResponseBase, UserPublic, ListResponse,
    Group, Object, ObjectType, )
from models.user import (
    UserAdminUpdateRequest, UserCalibrateResponse,
)
from utils import Password, http_exceptions

admin_user_router = APIRouter(
    prefix="/user",
    tags=["admin", "admin_user"],
)


@admin_user_router.get(
    path='/info/{user_id}',
    summary='获取用户信息',
    description='Get user information by ID',
    dependencies=[Depends(admin_required)],
)
async def router_admin_get_user(session: SessionDep, user_id: int) -> ResponseBase:
    """
    根据用户ID获取用户信息，包括用户名、邮箱、注册时间等。

    Args:
        session(SessionDep): 数据库会话依赖项。
        user_id (int): 用户ID。

    Returns:
        ResponseBase: 包含用户信息的响应模型。
    """
    user = await User.get_exist_one(session, user_id)
    return ResponseBase(data=user.to_public().model_dump())


@admin_user_router.get(
    path='/list',
    summary='获取用户列表',
    description='Get user list',
    dependencies=[Depends(admin_required)],
)
async def router_admin_get_users(
    session: SessionDep,
    table_view: TableViewRequestDep,
    filter_params: UserFilterParamsDep,
) -> ListResponse[UserPublic]:
    """
    获取用户列表，支持分页、排序、时间筛选和用户筛选。

    :param session: 数据库会话依赖项
    :param table_view: 分页排序参数依赖
    :param filter_params: 用户筛选参数（用户组、用户名、昵称、状态）
    :return: 分页用户列表
    """
    result = await User.get_with_count(session, filter_params=filter_params, table_view=table_view)
    return ListResponse(
        items=[user.to_public() for user in result.items],
        count=result.count,
    )


@admin_user_router.post(
    path='/create',
    summary='创建用户',
    description='Create a new user',
    dependencies=[Depends(admin_required)],
)
async def router_admin_create_user(
    session: SessionDep,
    user: User,
) -> ResponseBase:
    """
    创建一个新的用户，设置用户名、密码等信息。

    Returns:
        ResponseBase: 包含创建结果的响应模型。
    """
    existing_user = await User.get(session, User.username == user.username)
    if existing_user:
        return ResponseBase(
            code=400,
            msg="User with this username already exists."
        )
    user = await user.save(session)
    return ResponseBase(data=user.to_public().model_dump())


@admin_user_router.patch(
    path='/{user_id}',
    summary='更新用户信息',
    description='Update user information by ID',
    dependencies=[Depends(admin_required)],
)
async def router_admin_update_user(
    session: SessionDep,
    user_id: UUID,
    request: UserAdminUpdateRequest,
) -> ResponseBase:
    """
    根据用户ID更新用户信息。

    :param session: 数据库会话
    :param user_id: 用户UUID
    :param request: 更新请求
    :return: 更新结果
    """
    user = await User.get(session, User.id == user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 默认管理员（用户名为 admin）不允许更改用户组
    if request.group_id and user.username == "admin" and request.group_id != user.group_id:
        http_exceptions.raise_forbidden("默认管理员不允许更改用户组")

    # 如果更新用户组，验证新组存在
    if request.group_id:
        group = await Group.get(session, Group.id == request.group_id)
        if not group:
            raise HTTPException(status_code=400, detail="目标用户组不存在")

    # 如果更新密码，需要加密
    update_data = request.model_dump(exclude_unset=True)
    if 'password' in update_data and update_data['password']:
        update_data['password'] = Password.hash(update_data['password'])
    elif 'password' in update_data:
        del update_data['password']  # 空密码不更新

    # 验证两步验证密钥格式（如果提供了值且不为 None，长度必须为 32）
    if 'two_factor' in update_data and update_data['two_factor'] is not None:
        if len(update_data['two_factor']) != 32:
            raise HTTPException(status_code=400, detail="两步验证密钥必须为32位字符串")

    # 更新字段
    for key, value in update_data.items():
        setattr(user, key, value)
    user = await user.save(session)

    l.info(f"管理员更新了用户: {user.username}")
    return ResponseBase(data=user.to_public().model_dump())


@admin_user_router.delete(
    path='/{user_id}',
    summary='删除用户',
    description='Delete user by ID',
    dependencies=[Depends(admin_required)],
)
async def router_admin_delete_user(
    session: SessionDep,
    user_id: UUID,
) -> ResponseBase:
    """
    根据用户ID删除用户及其所有数据。

    注意: 这是一个危险操作，会级联删除用户的所有文件、分享、任务等。

    :param session: 数据库会话
    :param user_id: 用户UUID
    :return: 删除结果
    """
    user = await User.get(session, User.id == user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    username = user.username
    await User.delete(session, user)

    l.info(f"管理员删除了用户: {username}")
    return ResponseBase(data={"deleted": True})


@admin_user_router.post(
    path='/calibrate/{user_id}',
    summary='校准用户存储容量',
    description='Calibrate the user storage.',
    dependencies=[Depends(admin_required)]
)
async def router_admin_calibrate_storage(
    session: SessionDep,
    user_id: UUID,
) -> ResponseBase:
    """
    重新计算用户的已用存储空间。

    流程:
    1. 获取用户所有文件的大小总和
    2. 更新用户的 storage 字段
    3. 返回校准结果

    :param session: 数据库会话
    :param user_id: 用户UUID
    :return: 校准结果
    """
    user = await User.get(session, User.id == user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    previous_storage = user.storage

    # 计算实际存储量 - 使用 SQL 聚合
    from sqlmodel import select
    result = await session.execute(
        select(func.sum(Object.size), func.count(Object.id)).where(
            (Object.owner_id == user_id) & (Object.type == ObjectType.FILE)
        )
    )
    row = result.one()
    actual_storage = row[0] or 0
    file_count = row[1] or 0

    # 更新用户存储量
    user.storage = actual_storage
    user = await user.save(session)

    response = UserCalibrateResponse(
        user_id=user_id,
        previous_storage=previous_storage,
        current_storage=actual_storage,
        difference=actual_storage - previous_storage,
        file_count=file_count,
    )

    l.info(f"管理员校准了用户存储: {user.username}, 差值: {actual_storage - previous_storage}")
    return ResponseBase(data=response.model_dump())