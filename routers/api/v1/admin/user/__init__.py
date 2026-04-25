from uuid import UUID

from fastapi import APIRouter, Depends
from loguru import logger as l
from sqlalchemy import func
from sqlmodel_ext import rel

from middleware.scope import require_scope
from middleware.dependencies import SessionDep, ServerConfigDep, TableViewRequestDep, UserFilterParamsDep
from utils.redis.user_ban_store import UserBanStore
from sqlmodels import (
    User, UserPublic, ListResponse,
    Group, Entry, EntryType,
)
from sqlmodels.user import (
    UserAdminCreateRequest, UserAdminUpdateRequest, UserCalibrateResponse, UserStatus,
)
from utils import Password, http_exceptions
from utils.http.error_codes import ErrorCode as E

from .deps import build_user_filter_condition

admin_user_router = APIRouter(
    prefix="/user",
    tags=["admin", "admin_user"],
)


@admin_user_router.get(
    path='/',
    summary='获取用户列表',
    description='Get user list',
    dependencies=[Depends(require_scope("admin.users:read:all"))],
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
    condition = build_user_filter_condition(filter_params)
    result = await User.get_with_count(session, condition, table_view=table_view, load=rel(User.group))
    return ListResponse(
        items=[
            UserPublic.model_validate(
                user,
                from_attributes=True,
                update={'group_name': user.group.name if user.group else ""},
            )
            for user in result.items
        ],
        count=result.count,
    )


@admin_user_router.get(
    path='/{user_id}',
    summary='获取用户信息',
    description='Get user information by ID',
    dependencies=[Depends(require_scope("admin.users:read:all"))],
)
async def router_admin_get_user(session: SessionDep, user_id: UUID) -> UserPublic:
    """
    根据用户ID获取用户信息，包括用户名、邮箱、注册时间等。

    Args:
        session(SessionDep): 数据库会话依赖项。
        user_id (UUID): 用户ID。

    Returns:
        ResponseBase: 包含用户信息的响应模型。
    """
    user = await User.get_exist_one(session, user_id, load=rel(User.group))
    return UserPublic.model_validate(
        user,
        from_attributes=True,
        update={'group_name': user.group.name if user.group else ""},
    )


@admin_user_router.post(
    path='/',
    summary='创建用户',
    description='Create a new user',
    dependencies=[Depends(require_scope("admin.users:create:all"))],
)
async def router_admin_create_user(
    session: SessionDep,
    request: UserAdminCreateRequest,
) -> UserPublic:
    """
    创建一个新的用户，设置邮箱、密码、用户组等信息。

    管理员创建用户时，若提供了 email + password，
    会同时创建 AuthIdentity(provider=email_password)。

    :param session: 数据库会话
    :param request: 创建用户请求 DTO
    :return: 创建结果
    """
    # 如果提供了邮箱，检查唯一性
    if request.email:
        existing_user = await User.get(session, User.email == request.email)
        if existing_user:
            http_exceptions.raise_conflict(E.USER_EMAIL_EXISTS, "该邮箱已被注册")

    # 验证用户组存在
    group = await Group.get(session, Group.id == request.group_id)
    if not group:
        http_exceptions.raise_bad_request(E.ADMIN_GROUP_NOT_FOUND, "目标用户组不存在")

    user = User(
        email=request.email,
        nickname=request.nickname,
        group_id=request.group_id,
        password_hash=Password.hash(request.password) if request.password else None,
    )
    user = await user.save(session, load=rel(User.group))

    user = await User.get(session, User.id == user.id, load=rel(User.group))
    return UserPublic.model_validate(
        user,
        from_attributes=True,
        update={'group_name': user.group.name if user.group else ""},
    )


@admin_user_router.patch(
    path='/{user_id}',
    summary='更新用户信息',
    description='Update user information by ID',
    dependencies=[Depends(require_scope("admin.users:write:all"))],
    status_code=204
)
async def router_admin_update_user(
    session: SessionDep,
    config: ServerConfigDep,
    user_id: UUID,
    request: UserAdminUpdateRequest,
) -> None:
    """
    根据用户ID更新用户信息。

    :param session: 数据库会话
    :param config: 服务器配置
    :param user_id: 用户UUID
    :param request: 更新请求
    :return: 更新结果
    """
    user = await User.get_exist_one(session, user_id)

    # 默认管理员不允许更改用户组
    if (request.group_id
            and config.default_admin_id == user_id
            and request.group_id != user.group_id):
        http_exceptions.raise_forbidden(E.ADMIN_GROUP_DEFAULT_IMMUTABLE, "默认管理员不允许更改用户组")

    # 如果更新用户组，验证新组存在
    if request.group_id:
        group = await Group.get(session, Group.id == request.group_id)
        if not group:
            http_exceptions.raise_bad_request(E.ADMIN_GROUP_NOT_FOUND, "目标用户组不存在")

    update_data = request.model_dump(exclude_unset=True)

    # 记录旧 status 以便检测变更
    old_status = user.status

    # 更新字段
    for key, value in update_data.items():
        setattr(user, key, value)
    user = await user.save(session)

    # 封禁状态变更 → 更新 BanStore
    new_status = user.status
    if old_status == UserStatus.ACTIVE and new_status != UserStatus.ACTIVE:
        await UserBanStore.ban(str(user_id))
    elif old_status != UserStatus.ACTIVE and new_status == UserStatus.ACTIVE:
        await UserBanStore.unban(str(user_id))

    l.info(f"管理员更新了用户: {user.email}")


@admin_user_router.delete(
    path='/',
    summary='删除用户（支持批量）',
    description='Delete users by ID list',
    dependencies=[Depends(require_scope("admin.users:delete:all"))],
    status_code=204,
)
async def router_admin_delete_users(
    session: SessionDep,
    config: ServerConfigDep,
) -> None:
    """
    批量删除用户及其所有数据。

    注意: 这是一个危险操作，会级联删除用户的所有文件、分享、任务等。

    :param session: 数据库会话
    :param config: 服务器配置
    :param request: 批量删除请求，包含待删除用户的 UUID 列表
    :return: 删除结果（已删除数 / 总请求数）
    """
    http_exceptions.raise_service_unavailable(E.ADMIN_SLAVE_CONNECTION_FAILED)
    # for uid in request.ids:
    #     user = await User.get(session, User.id == uid, load=User.group)

    #     # 安全检查：默认管理员不允许被删除
    #     if user and config.default_admin_id == uid:
    #         raise HTTPException(status_code=403, detail=f"默认管理员不允许被删除")

    #     if user:
    #         await User.delete(session, user)
    #         l.info(f"管理员删除了用户: {user.email}")


@admin_user_router.post(
    path='/calibrate/{user_id}',
    summary='校准用户存储容量',
    description='Calibrate the user storage.',
    dependencies=[Depends(require_scope("admin.users:write:all"))]
)
async def router_admin_calibrate_storage(
    session: SessionDep,
    user_id: UUID,
) -> UserCalibrateResponse:
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
    user = await User.get_exist_one(session, user_id)

    previous_storage = user.storage

    # 计算实际存储量 - 使用 SQL 聚合
    # [TODO] 不应这么计算，看看 SQLModel_Ext 库怎么解决
    from sqlmodel import select
    result = await session.execute(
        select(func.sum(Entry.size), func.count(Entry.id)).where(
            (Entry.owner_id == user_id) & (Entry.type == EntryType.FILE)
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

    l.info(f"管理员校准了用户存储: {user.email}, 差值: {actual_storage - previous_storage}")
    return response