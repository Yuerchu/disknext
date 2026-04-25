from uuid import UUID

from fastapi import APIRouter, Depends
from loguru import logger as l
from sqlmodel_ext import cond, rel

from middleware.scope import require_scope
from middleware.dependencies import SessionDep, TableViewRequestDep
from sqlmodels import (
    User, UserPublic, ListResponse,
    Group )
from sqlmodels.group import (
    GroupCreateRequest, GroupUpdateRequest, GroupDetailResponse, )
from sqlmodels.policy import GroupPolicyLink
from utils import http_exceptions
from utils.http.error_codes import ErrorCode as E

admin_group_router = APIRouter(
    prefix="/group",
    tags=["admin", "admin_group"],
)

@admin_group_router.get(
    path='/',
    summary='获取用户组列表',
    description='Get user group list',
    dependencies=[Depends(require_scope("admin.groups:read:all"))],
)
async def router_admin_get_groups(
    session: SessionDep,
    table_view: TableViewRequestDep,
) -> ListResponse[GroupDetailResponse]:
    """
    获取用户组列表，支持分页、排序和时间筛选。

    :param session: 数据库会话
    :param table_view: 分页排序参数依赖
    :return: 分页用户组列表
    """
    result = await Group.get_with_count(session, table_view=table_view, load=rel(Group.policies))

    # 构建响应
    items: list[GroupDetailResponse] = []
    for g in result.items:
        policies = g.policies
        user_count = await User.count(session, cond(User.group_id == g.id))
        items.append(GroupDetailResponse.model_validate(g, from_attributes=True, update={
            'user_count': user_count,
            'policy_ids': [p.id for p in policies],
        }))

    return ListResponse(items=items, count=result.count)


@admin_group_router.get(
    path='/{group_id}',
    summary='获取用户组信息',
    description='Get user group information by ID',
    dependencies=[Depends(require_scope("admin.groups:read:all"))],
)
async def router_admin_get_group(
    session: SessionDep,
    group_id: UUID,
) -> GroupDetailResponse:
    """
    根据用户组ID获取用户组详细信息。

    :param session: 数据库会话
    :param group_id: 用户组UUID
    :return: 用户组详情
    """
    group = await Group.get_exist_one(session, group_id, load=rel(Group.policies))

    user_count = await User.count(session, cond(User.group_id == group_id))
    return GroupDetailResponse.model_validate(group, from_attributes=True, update={
        'user_count': user_count,
        'policy_ids': [p.id for p in group.policies],
    })


@admin_group_router.get(
    path='/list/{group_id}',
    summary='获取用户组成员列表',
    description='Get user group member list by group ID',
    dependencies=[Depends(require_scope("admin.groups:read:all"))],
)
async def router_admin_get_group_members(
    session: SessionDep,
    group_id: UUID,
    table_view: TableViewRequestDep,
) -> ListResponse[UserPublic]:
    """
    根据用户组ID获取用户组成员列表。

    :param session: 数据库会话
    :param group_id: 用户组UUID
    :param table_view: 分页排序参数依赖
    :return: 分页成员列表
    """
    # 验证组存在
    _ = await Group.get_exist_one(session, group_id)

    result = await User.get_with_count(
        session, cond(User.group_id == group_id), table_view=table_view,
        load=rel(User.group),
    )

    return ListResponse(
        items=[
            UserPublic.model_validate(
                u,
                from_attributes=True,
                update={'group_name': u.group.name if u.group else ""},
            )
            for u in result.items
        ],
        count=result.count,
    )


@admin_group_router.post(
    path='/',
    summary='创建用户组',
    description='Create a new user group',
    dependencies=[Depends(require_scope("admin.groups:create:all"))],
    status_code=204,
)
async def router_admin_create_group(
    session: SessionDep,
    request: GroupCreateRequest,
) -> None:
    """
    创建新的用户组。

    :param session: 数据库会话
    :param request: 创建请求
    :return: 创建结果
    """
    # 检查名称唯一性
    existing = await Group.get(session, Group.name == request.name)
    if existing:
        http_exceptions.raise_conflict(E.ADMIN_GROUP_NAME_EXISTS, "用户组名称已存在")

    # 创建用户组（选项字段已合并到 Group 表）
    group = Group(**request.model_dump(exclude={'policy_ids'}))
    group = await group.save(session)
    group_id_val: UUID = group.id

    # 关联存储策略
    for policy_id in request.policy_ids:
        link = GroupPolicyLink(group_id=group_id_val, policy_id=policy_id)
        session.add(link)
    await session.commit()

    l.info(f"管理员创建了用户组: {group.name}")


@admin_group_router.patch(
    path='/{group_id}',
    summary='更新用户组信息',
    description='Update user group information by ID',
    dependencies=[Depends(require_scope("admin.groups:write:all"))],
    status_code=204,
)
async def router_admin_update_group(
    session: SessionDep,
    group_id: UUID,
    request: GroupUpdateRequest,
) -> None:
    """
    根据用户组ID更新用户组信息。

    :param session: 数据库会话
    :param group_id: 用户组UUID
    :param request: 更新请求
    :return: 更新结果
    """
    group = await Group.get_exist_one(session, group_id)

    # 检查名称唯一性（如果要更新名称）
    if request.name and request.name != group.name:
        existing = await Group.get(session, Group.name == request.name)
        if existing:
            http_exceptions.raise_conflict(E.ADMIN_GROUP_NAME_EXISTS, "用户组名称已存在")

    # 更新字段（选项字段已合并到 Group 表，统一处理）
    update_data = request.model_dump(exclude_unset=True, exclude={'policy_ids'})
    if update_data:
        for key, value in update_data.items():
            if value is not None:
                setattr(group, key, value)
        group = await group.save(session)

    # 更新策略关联
    if request.policy_ids is not None:
        _ = await GroupPolicyLink.delete(
            session,
            condition=cond(GroupPolicyLink.group_id == group_id)
        )
        for policy_id in request.policy_ids:
            link = GroupPolicyLink(group_id=group_id, policy_id=policy_id)
            session.add(link)
        await session.commit()

    l.info(f"管理员更新了用户组: {group_id}")


@admin_group_router.delete(
    path='/{group_id}',
    summary='删除用户组',
    description='Delete user group by ID',
    dependencies=[Depends(require_scope("admin.groups:delete:all"))],
    status_code=204,
)
async def router_admin_delete_group(
    session: SessionDep,
    group_id: UUID,
) -> None:
    """
    根据用户组ID删除用户组。

    注意: 如果有用户属于该组，需要先迁移用户或拒绝删除。

    :param session: 数据库会话
    :param group_id: 用户组UUID
    :return: 删除结果
    """
    group = await Group.get_exist_one(session, group_id)

    # 检查是否有用户属于该组
    user_count = await User.count(session, User.group_id == group_id)
    if user_count > 0:
        http_exceptions.raise_bad_request(
            E.ADMIN_GROUP_HAS_USERS,
            f"无法删除，该组下还有 {user_count} 个用户",
        )

    _ = await Group.delete(session, group)

    l.info(f"管理员删除了用户组: {group_id}")
