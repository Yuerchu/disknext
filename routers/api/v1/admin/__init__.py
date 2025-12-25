from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from loguru import logger as l
from sqlalchemy import func, and_
from sqlmodel import Field

from middleware.auth import AdminRequired
from middleware.dependencies import SessionDep
from models import (
    Policy, PolicyOptions, PolicyType, User, ResponseBase,
    Group, GroupOptions, Setting, Object, ObjectType, Share, Task,
)
from models.base import SQLModelBase
from models.group import (
    GroupCreateRequest, GroupUpdateRequest, GroupDetailResponse, GroupListResponse,
)
from models.user import (
    UserPublic, UserAdminUpdateRequest, UserCalibrateResponse,
)
from models.setting import SettingsUpdateRequest, SettingsGetResponse
from models.object import AdminFileResponse, AdminFileListResponse, FileBanRequest
from models.policy import GroupPolicyLink
from service.storage import DirectoryCreationError, LocalStorageService
from utils import Password


class PolicyTestPathRequest(SQLModelBase):
    """测试本地路径请求 DTO"""

    path: str = Field(max_length=512)
    """要测试的本地路径"""


class PolicyTestSlaveRequest(SQLModelBase):
    """测试从机通信请求 DTO"""

    server: str = Field(max_length=255)
    """从机服务器地址"""

    secret: str
    """从机通信密钥"""


class Aria2TestRequest(SQLModelBase):
    """Aria2 测试请求 DTO"""

    rpc_url: str
    """RPC 地址"""

    secret: str | None = None
    """RPC 密钥"""


class PolicyCreateRequest(SQLModelBase):
    """创建存储策略请求 DTO"""

    name: str = Field(max_length=255)
    """策略名称"""

    type: PolicyType
    """策略类型"""

    server: str | None = Field(default=None, max_length=255)
    """服务器地址/本地路径（本地存储必填）"""

    bucket_name: str | None = Field(default=None, max_length=255)
    """存储桶名称（S3必填）"""

    is_private: bool = True
    """是否为私有空间"""

    base_url: str | None = Field(default=None, max_length=255)
    """访问文件的基础URL"""

    access_key: str | None = None
    """Access Key"""

    secret_key: str | None = None
    """Secret Key"""

    max_size: int = Field(default=0, ge=0)
    """允许上传的最大文件尺寸（字节），0表示不限制"""

    auto_rename: bool = False
    """是否自动重命名"""

    dir_name_rule: str | None = Field(default=None, max_length=255)
    """目录命名规则"""

    file_name_rule: str | None = Field(default=None, max_length=255)
    """文件命名规则"""

    is_origin_link_enable: bool = False
    """是否开启源链接访问"""

# 管理员根目录 /api/admin
admin_router = APIRouter(
    prefix="/admin",
    tags=["admin"],
)

# 用户组 /api/admin/group
admin_group_router = APIRouter(
    prefix="/admin/group",
    tags=["admin", "admin_group"],
)

# 用户 /api/admin/user
admin_user_router = APIRouter(
    prefix="/admin/user",
    tags=["admin", "admin_user"],
)

# 文件 /api/admin/file
admin_file_router = APIRouter(
    prefix="/admin/file",
    tags=["admin", "admin_file"],
)

# 离线下载 /api/admin/aria2
admin_aria2_router = APIRouter(
    prefix='/admin/aria2',
    tags=['admin', 'admin_aria2']
)

# 存储策略管理 /api/admin/policy
admin_policy_router = APIRouter(
    prefix='/admin/policy',
    tags=['admin', 'admin_policy']
)

# 分享 /api/admin/share
admin_share_router = APIRouter(
    prefix='/admin/share',
    tags=['admin', 'admin_share']
)

# 任务 /api/admin/task
admin_task_router = APIRouter(
    prefix='/admin/task',
    tags=['admin', 'admin_task']
)

# 增值服务 /api/admin/vas
admin_vas_router = APIRouter(
    prefix='/admin/vas',
    tags=['admin', 'admin_vas']
)


@admin_router.get(
    path='/summary',
    summary='获取站点概况',
    description='Get site summary information',
    dependencies=[Depends(AdminRequired)],
)
def router_admin_get_summary() -> ResponseBase:
    """
    获取站点概况信息，包括用户数、分享数、文件数等。
    
    Returns:
        ResponseBase: 包含站点概况信息的响应模型。
    """
    pass

@admin_router.get(
    path='/news',
    summary='获取社区新闻',
    description='Get community news',
    dependencies=[Depends(AdminRequired)],
)
def router_admin_get_news() -> ResponseBase:
    """
    获取社区新闻信息，包括最新的动态和公告。
    
    Returns:
        ResponseBase: 包含社区新闻信息的响应模型。
    """
    pass

@admin_router.patch(
    path='/settings',
    summary='更新设置',
    description='Update settings',
    dependencies=[Depends(AdminRequired)],
)
async def router_admin_update_settings(
    session: SessionDep,
    request: SettingsUpdateRequest,
) -> ResponseBase:
    """
    批量更新站点设置。

    :param session: 数据库会话
    :param request: 更新请求，按类型分组的设置项
    :return: 更新结果
    """
    updated_count = 0

    for setting_type, items in request.settings.items():
        for name, value in items.items():
            existing = await Setting.get(
                session,
                and_(Setting.type == setting_type, Setting.name == name)
            )

            if existing:
                existing.value = value
                await existing.save(session)
            else:
                new_setting = Setting(type=setting_type, name=name, value=value)
                await new_setting.save(session)

            updated_count += 1

    l.info(f"管理员更新了 {updated_count} 个设置项")
    return ResponseBase(data={"updated": updated_count})


@admin_router.get(
    path='/settings',
    summary='获取设置',
    description='Get settings',
    dependencies=[Depends(AdminRequired)],
)
async def router_admin_get_settings(session: SessionDep) -> ResponseBase:
    """
    获取所有站点设置，按类型分组返回。

    :param session: 数据库会话
    :return: 按类型分组的设置项
    """
    settings = await Setting.get(session, None, fetch_mode="all")

    # 按 type 分组
    grouped: dict[str, dict[str, str | None]] = {}
    for setting in settings:
        if setting.type not in grouped:
            grouped[setting.type] = {}
        grouped[setting.type][setting.name] = setting.value

    return ResponseBase(data=grouped)

@admin_group_router.get(
    path='/',
    summary='获取用户组列表',
    description='Get user group list',
    dependencies=[Depends(AdminRequired)],
)
async def router_admin_get_groups(
    session: SessionDep,
    page: int = 1,
    page_size: int = 20,
) -> ResponseBase:
    """
    获取用户组列表，支持分页。

    :param session: 数据库会话
    :param page: 页码
    :param page_size: 每页数量
    :return: 用户组列表
    """
    offset = (page - 1) * page_size

    groups = await Group.get(
        session,
        None,
        fetch_mode="all",
        offset=offset,
        limit=page_size,
        load=Group.options,
    )

    total = await Group.count(session, None)

    # 构建响应
    group_list = []
    for g in groups:
        opts = g.options
        policies = await g.awaitable_attrs.policies
        user_count = await User.count(session, User.group_id == g.id)

        group_list.append(GroupDetailResponse(
            id=g.id,
            name=g.name,
            max_storage=g.max_storage,
            share_enabled=g.share_enabled,
            web_dav_enabled=g.web_dav_enabled,
            admin=g.admin,
            speed_limit=g.speed_limit,
            user_count=user_count,
            policy_ids=[p.id for p in policies],
            share_download=opts.share_download if opts else False,
            share_free=opts.share_free if opts else False,
            relocate=opts.relocate if opts else False,
            source_batch=opts.source_batch if opts else 0,
            select_node=opts.select_node if opts else False,
            advance_delete=opts.advance_delete if opts else False,
            archive_download=opts.archive_download if opts else False,
            archive_task=opts.archive_task if opts else False,
            webdav_proxy=opts.webdav_proxy if opts else False,
            aria2=opts.aria2 if opts else False,
            redirected_source=opts.redirected_source if opts else False,
        ).model_dump())

    return ResponseBase(data={"groups": group_list, "total": total})


@admin_group_router.get(
    path='/{group_id}',
    summary='获取用户组信息',
    description='Get user group information by ID',
    dependencies=[Depends(AdminRequired)],
)
async def router_admin_get_group(
    session: SessionDep,
    group_id: UUID,
) -> ResponseBase:
    """
    根据用户组ID获取用户组详细信息。

    :param session: 数据库会话
    :param group_id: 用户组UUID
    :return: 用户组详情
    """
    group = await Group.get(session, Group.id == group_id, load=Group.options)

    if not group:
        raise HTTPException(status_code=404, detail="用户组不存在")

    opts = group.options
    policies = await group.awaitable_attrs.policies
    user_count = await User.count(session, User.group_id == group_id)

    response = GroupDetailResponse(
        id=group.id,
        name=group.name,
        max_storage=group.max_storage,
        share_enabled=group.share_enabled,
        web_dav_enabled=group.web_dav_enabled,
        admin=group.admin,
        speed_limit=group.speed_limit,
        user_count=user_count,
        policy_ids=[p.id for p in policies],
        share_download=opts.share_download if opts else False,
        share_free=opts.share_free if opts else False,
        relocate=opts.relocate if opts else False,
        source_batch=opts.source_batch if opts else 0,
        select_node=opts.select_node if opts else False,
        advance_delete=opts.advance_delete if opts else False,
        archive_download=opts.archive_download if opts else False,
        archive_task=opts.archive_task if opts else False,
        webdav_proxy=opts.webdav_proxy if opts else False,
        aria2=opts.aria2 if opts else False,
        redirected_source=opts.redirected_source if opts else False,
    )

    return ResponseBase(data=response.model_dump())


@admin_group_router.get(
    path='/list/{group_id}',
    summary='获取用户组成员列表',
    description='Get user group member list by group ID',
    dependencies=[Depends(AdminRequired)],
)
async def router_admin_get_group_members(
    session: SessionDep,
    group_id: UUID,
    page: int = 1,
    page_size: int = 20,
) -> ResponseBase:
    """
    根据用户组ID获取用户组成员列表。

    :param session: 数据库会话
    :param group_id: 用户组UUID
    :param page: 页码
    :param page_size: 每页数量
    :return: 成员列表
    """
    # 验证组存在
    group = await Group.get(session, Group.id == group_id)
    if not group:
        raise HTTPException(status_code=404, detail="用户组不存在")

    offset = (page - 1) * page_size

    users = await User.get(
        session,
        User.group_id == group_id,
        fetch_mode="all",
        offset=offset,
        limit=page_size,
    )

    total = await User.count(session, User.group_id == group_id)

    return ResponseBase(data={
        "members": [u.to_public().model_dump() for u in users],
        "total": total,
    })


@admin_group_router.post(
    path='/',
    summary='创建用户组',
    description='Create a new user group',
    dependencies=[Depends(AdminRequired)],
)
async def router_admin_create_group(
    session: SessionDep,
    request: GroupCreateRequest,
) -> ResponseBase:
    """
    创建新的用户组。

    :param session: 数据库会话
    :param request: 创建请求
    :return: 创建结果
    """
    # 检查名称唯一性
    existing = await Group.get(session, Group.name == request.name)
    if existing:
        raise HTTPException(status_code=409, detail="用户组名称已存在")

    # 创建用户组
    group = Group(
        name=request.name,
        max_storage=request.max_storage,
        share_enabled=request.share_enabled,
        web_dav_enabled=request.web_dav_enabled,
        speed_limit=request.speed_limit,
    )
    group = await group.save(session)

    # 创建选项
    options = GroupOptions(
        group_id=group.id,
        share_download=request.share_download,
        share_free=request.share_free,
        relocate=request.relocate,
        source_batch=request.source_batch,
        select_node=request.select_node,
        advance_delete=request.advance_delete,
        archive_download=request.archive_download,
        archive_task=request.archive_task,
        webdav_proxy=request.webdav_proxy,
        aria2=request.aria2,
        redirected_source=request.redirected_source,
    )
    await options.save(session)

    # 关联存储策略
    for policy_id in request.policy_ids:
        link = GroupPolicyLink(group_id=group.id, policy_id=policy_id)
        session.add(link)
    await session.commit()

    l.info(f"管理员创建了用户组: {group.name}")
    return ResponseBase(data={"id": str(group.id), "name": group.name})


@admin_group_router.patch(
    path='/{group_id}',
    summary='更新用户组信息',
    description='Update user group information by ID',
    dependencies=[Depends(AdminRequired)],
)
async def router_admin_update_group(
    session: SessionDep,
    group_id: UUID,
    request: GroupUpdateRequest,
) -> ResponseBase:
    """
    根据用户组ID更新用户组信息。

    :param session: 数据库会话
    :param group_id: 用户组UUID
    :param request: 更新请求
    :return: 更新结果
    """
    group = await Group.get(session, Group.id == group_id, load=Group.options)
    if not group:
        raise HTTPException(status_code=404, detail="用户组不存在")

    # 检查名称唯一性（如果要更新名称）
    if request.name and request.name != group.name:
        existing = await Group.get(session, Group.name == request.name)
        if existing:
            raise HTTPException(status_code=409, detail="用户组名称已存在")

    # 更新组基础字段
    update_data = request.model_dump(
        exclude_unset=True,
        exclude={'policy_ids', 'share_download', 'share_free', 'relocate',
                 'source_batch', 'select_node', 'advance_delete', 'archive_download',
                 'archive_task', 'webdav_proxy', 'aria2', 'redirected_source'}
    )
    if update_data:
        for key, value in update_data.items():
            setattr(group, key, value)
        group = await group.save(session)

    # 更新选项
    if group.options:
        options_fields = {'share_download', 'share_free', 'relocate', 'source_batch',
                         'select_node', 'advance_delete', 'archive_download',
                         'archive_task', 'webdav_proxy', 'aria2', 'redirected_source'}
        options_data = {k: v for k, v in request.model_dump(exclude_unset=True).items()
                       if k in options_fields and v is not None}
        if options_data:
            for key, value in options_data.items():
                setattr(group.options, key, value)
            await group.options.save(session)

    # 更新策略关联
    if request.policy_ids is not None:
        # 删除旧关联
        from sqlmodel import select, delete
        await session.execute(
            delete(GroupPolicyLink).where(GroupPolicyLink.group_id == group_id)
        )
        # 添加新关联
        for policy_id in request.policy_ids:
            link = GroupPolicyLink(group_id=group_id, policy_id=policy_id)
            session.add(link)
        await session.commit()

    l.info(f"管理员更新了用户组: {group.name}")
    return ResponseBase(data={"id": str(group.id)})


@admin_group_router.delete(
    path='/{group_id}',
    summary='删除用户组',
    description='Delete user group by ID',
    dependencies=[Depends(AdminRequired)],
)
async def router_admin_delete_group(
    session: SessionDep,
    group_id: UUID,
) -> ResponseBase:
    """
    根据用户组ID删除用户组。

    注意: 如果有用户属于该组，需要先迁移用户或拒绝删除。

    :param session: 数据库会话
    :param group_id: 用户组UUID
    :return: 删除结果
    """
    group = await Group.get(session, Group.id == group_id)
    if not group:
        raise HTTPException(status_code=404, detail="用户组不存在")

    # 检查是否有用户属于该组
    user_count = await User.count(session, User.group_id == group_id)
    if user_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"无法删除，该组下还有 {user_count} 个用户"
        )

    group_name = group.name
    await Group.delete(session, group)

    l.info(f"管理员删除了用户组: {group_name}")
    return ResponseBase(data={"deleted": True})

@admin_user_router.get(
    path='/info/{user_id}',
    summary='获取用户信息',
    description='Get user information by ID',
    dependencies=[Depends(AdminRequired)],
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
    dependencies=[Depends(AdminRequired)],
)
async def router_admin_get_users(
    session: SessionDep,
    page: int = 1,
    page_size: int = 20
) -> ResponseBase:
    """
    获取用户列表，支持分页。

    Args:
        session: 数据库会话依赖项。
        page (int): 页码，默认为1。
        page_size (int): 每页显示的用户数量，默认为20。

    Returns:
        ResponseBase: 包含用户列表的响应模型。
    """
    offset = (page - 1) * page_size
    users: list[User] = await User.get(
        session,
        None,
        fetch_mode="all",
        offset=offset,
        limit=page_size
    )
    return ResponseBase(
        data=[user.to_public().model_dump() for user in users]
    )

@admin_user_router.post(
    path='/create',
    summary='创建用户',
    description='Create a new user',
    dependencies=[Depends(AdminRequired)],
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
    dependencies=[Depends(AdminRequired)],
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
    dependencies=[Depends(AdminRequired)],
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
    dependencies=[Depends(AdminRequired)]
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
            and_(Object.owner_id == user_id, Object.type == ObjectType.FILE)
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

@admin_file_router.get(
    path='/list',
    summary='获取文件列表',
    description='Get file list',
    dependencies=[Depends(AdminRequired)],
)
async def router_admin_get_file_list(
    session: SessionDep,
    user_id: UUID | None = None,
    is_banned: bool | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> ResponseBase:
    """
    获取系统中的文件列表，支持筛选。

    :param session: 数据库会话
    :param user_id: 按用户筛选
    :param is_banned: 按封禁状态筛选
    :param keyword: 按文件名搜索
    :param page: 页码
    :param page_size: 每页数量
    :return: 文件列表
    """
    offset = (page - 1) * page_size

    # 构建查询条件
    conditions = [Object.type == ObjectType.FILE]
    if user_id:
        conditions.append(Object.owner_id == user_id)
    if is_banned is not None:
        conditions.append(Object.is_banned == is_banned)
    if keyword:
        conditions.append(Object.name.ilike(f"%{keyword}%"))

    combined_condition = and_(*conditions) if len(conditions) > 1 else conditions[0]

    files = await Object.get(
        session,
        combined_condition,
        fetch_mode="all",
        offset=offset,
        limit=page_size,
        load=Object.owner,
    )

    total = await Object.count(session, combined_condition)

    # 构建响应
    file_list = []
    for f in files:
        owner = await f.awaitable_attrs.owner
        policy = await f.awaitable_attrs.policy
        file_list.append(AdminFileResponse(
            id=f.id,
            name=f.name,
            type=f.type,
            size=f.size,
            thumb=False,
            date=f.updated_at,
            create_date=f.created_at,
            source_enabled=False,
            owner_id=f.owner_id,
            owner_username=owner.username if owner else "unknown",
            policy_name=policy.name if policy else "unknown",
            is_banned=f.is_banned,
            banned_at=f.banned_at,
            ban_reason=f.ban_reason,
        ).model_dump())

    return ResponseBase(data={"files": file_list, "total": total})


@admin_file_router.get(
    path='/preview/{file_id}',
    summary='预览文件',
    description='Preview file by ID',
    dependencies=[Depends(AdminRequired)],
)
async def router_admin_preview_file(
    session: SessionDep,
    file_id: UUID,
) -> FileResponse:
    """
    管理员预览文件内容。

    :param session: 数据库会话
    :param file_id: 文件UUID
    :return: 文件内容
    """
    file_obj = await Object.get(session, Object.id == file_id)
    if not file_obj:
        raise HTTPException(status_code=404, detail="文件不存在")

    if not file_obj.is_file:
        raise HTTPException(status_code=400, detail="对象不是文件")

    # 获取物理文件
    physical_file = await file_obj.awaitable_attrs.physical_file
    if not physical_file or not physical_file.storage_path:
        raise HTTPException(status_code=500, detail="文件存储路径丢失")

    policy = await Policy.get(session, Policy.id == file_obj.policy_id)
    if not policy:
        raise HTTPException(status_code=500, detail="存储策略不存在")

    if policy.type == PolicyType.LOCAL:
        storage_service = LocalStorageService(policy)
        if not await storage_service.file_exists(physical_file.storage_path):
            raise HTTPException(status_code=404, detail="物理文件不存在")

        return FileResponse(
            path=physical_file.storage_path,
            filename=file_obj.name,
        )
    else:
        raise HTTPException(status_code=501, detail="S3 存储暂未实现")


@admin_file_router.patch(
    path='/ban/{file_id}',
    summary='封禁/解禁文件',
    description='Ban the file, user can\'t open, copy, move, download or share this file if administrator ban.',
    dependencies=[Depends(AdminRequired)],
)
async def router_admin_ban_file(
    session: SessionDep,
    file_id: UUID,
    request: FileBanRequest,
    admin: Annotated[User, Depends(AdminRequired)],
) -> ResponseBase:
    """
    封禁或解禁文件。封禁后用户无法访问该文件。

    :param session: 数据库会话
    :param file_id: 文件UUID
    :param request: 封禁请求
    :param admin: 当前管理员
    :return: 封禁结果
    """
    file_obj = await Object.get(session, Object.id == file_id)
    if not file_obj:
        raise HTTPException(status_code=404, detail="文件不存在")

    file_obj.is_banned = request.is_banned
    if request.is_banned:
        file_obj.banned_at = datetime.now()
        file_obj.banned_by = admin.id
        file_obj.ban_reason = request.reason
    else:
        file_obj.banned_at = None
        file_obj.banned_by = None
        file_obj.ban_reason = None

    file_obj = await file_obj.save(session)

    action = "封禁" if request.is_banned else "解禁"
    l.info(f"管理员{action}了文件: {file_obj.name}")
    return ResponseBase(data={
        "id": str(file_obj.id),
        "is_banned": file_obj.is_banned,
    })


@admin_file_router.delete(
    path='/{file_id}',
    summary='删除文件',
    description='Delete file by ID',
    dependencies=[Depends(AdminRequired)],
)
async def router_admin_delete_file(
    session: SessionDep,
    file_id: UUID,
    delete_physical: bool = True,
) -> ResponseBase:
    """
    删除文件。

    :param session: 数据库会话
    :param file_id: 文件UUID
    :param delete_physical: 是否同时删除物理文件
    :return: 删除结果
    """
    file_obj = await Object.get(session, Object.id == file_id)
    if not file_obj:
        raise HTTPException(status_code=404, detail="文件不存在")

    if not file_obj.is_file:
        raise HTTPException(status_code=400, detail="对象不是文件")

    file_name = file_obj.name
    file_size = file_obj.size
    owner_id = file_obj.owner_id

    # 删除物理文件（可选）
    if delete_physical:
        physical_file = await file_obj.awaitable_attrs.physical_file
        if physical_file and physical_file.storage_path:
            policy = await Policy.get(session, Policy.id == file_obj.policy_id)
            if policy and policy.type == PolicyType.LOCAL:
                try:
                    storage_service = LocalStorageService(policy)
                    await storage_service.delete_file(physical_file.storage_path)
                except Exception as e:
                    l.warning(f"删除物理文件失败: {e}")

    # 更新用户存储量
    owner = await User.get(session, User.id == owner_id)
    if owner:
        owner.storage = max(0, owner.storage - file_size)
        await owner.save(session)

    await Object.delete(session, file_obj)

    l.info(f"管理员删除了文件: {file_name}")
    return ResponseBase(data={"deleted": True})

@admin_aria2_router.post(
    path='/test',
    summary='测试 Aria2 连接',
    description='Test Aria2 RPC connection',
    dependencies=[Depends(AdminRequired)]
)
async def router_admin_aira2_test(
    request: Aria2TestRequest,
) -> ResponseBase:
    """
    测试 Aria2 RPC 连接。

    :param request: 测试请求
    :return: 测试结果
    """
    import aiohttp

    try:
        payload = {
            "jsonrpc": "2.0",
            "id": "test",
            "method": "aria2.getVersion",
            "params": [f"token:{request.secret}"] if request.secret else [],
        }

        async with aiohttp.ClientSession() as client:
            async with client.post(request.rpc_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return ResponseBase(
                        code=400,
                        msg=f"连接失败，HTTP {resp.status}"
                    )

                result = await resp.json()
                if "error" in result:
                    return ResponseBase(
                        code=400,
                        msg=f"Aria2 错误: {result['error']['message']}"
                    )

                version = result.get("result", {}).get("version", "unknown")
                return ResponseBase(data={
                    "connected": True,
                    "version": version,
                })
    except Exception as e:
        return ResponseBase(code=400, msg=f"连接失败: {str(e)}")

@admin_policy_router.get(
    path='/list',
    summary='列出存储策略',
    description='List all storage policies',
    dependencies=[Depends(AdminRequired)]
)
async def router_policy_list(
    session: SessionDep,
    page: int = 1,
    page_size: int = 20,
) -> ResponseBase:
    """
    获取所有存储策略列表。

    :param session: 数据库会话
    :param page: 页码
    :param page_size: 每页数量
    :return: 策略列表
    """
    offset = (page - 1) * page_size

    policies = await Policy.get(
        session,
        None,
        fetch_mode="all",
        offset=offset,
        limit=page_size,
    )

    total = await Policy.count(session, None)

    return ResponseBase(data={
        "policies": [
            {
                "id": str(p.id),
                "name": p.name,
                "type": p.type.value,
                "server": p.server,
                "max_size": p.max_size,
                "is_private": p.is_private,
            }
            for p in policies
        ],
        "total": total,
    })


@admin_policy_router.post(
    path='/test/path',
    summary='测试本地路径可用性',
    description='Test local path availability',
    dependencies=[Depends(AdminRequired)]
)
async def router_policy_test_path(
    request: PolicyTestPathRequest,
) -> ResponseBase:
    """
    测试本地存储路径是否可用。

    :param request: 测试请求
    :return: 测试结果
    """
    import aiofiles.os
    from pathlib import Path

    path = Path(request.path).resolve()

    # 检查路径是否存在
    is_exists = await aiofiles.os.path.exists(str(path))

    # 检查是否可写
    is_writable = False
    if is_exists:
        test_file = path / ".write_test"
        try:
            async with aiofiles.open(str(test_file), 'w') as f:
                await f.write("test")
            await aiofiles.os.remove(str(test_file))
            is_writable = True
        except Exception:
            pass

    return ResponseBase(data={
        "path": str(path),
        "exists": is_exists,
        "writable": is_writable,
    })


@admin_policy_router.post(
    path='/test/slave',
    summary='测试从机通信',
    description='Test slave node communication',
    dependencies=[Depends(AdminRequired)]
)
async def router_policy_test_slave(
    request: PolicyTestSlaveRequest,
) -> ResponseBase:
    """
    测试从机RPC通信。

    :param request: 测试请求
    :return: 测试结果
    """
    import aiohttp

    try:
        async with aiohttp.ClientSession() as client:
            async with client.get(
                f"{request.server}/api/slave/ping",
                headers={"Authorization": request.secret},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    return ResponseBase(data={"connected": True})
                else:
                    return ResponseBase(
                        code=400,
                        msg=f"从机响应错误，HTTP {resp.status}"
                    )
    except Exception as e:
        return ResponseBase(code=400, msg=f"连接失败: {str(e)}")

@admin_policy_router.post(
    path='/',
    summary='创建存储策略',
    description='创建新的存储策略。对于本地存储策略，会自动创建物理目录。',
    dependencies=[Depends(AdminRequired)]
)
async def router_policy_add_policy(
    session: SessionDep,
    request: PolicyCreateRequest,
) -> ResponseBase:
    """
    创建存储策略端点

    功能：
    - 创建新的存储策略配置
    - 对于 LOCAL 类型，自动创建物理目录

    认证：
    - 需要管理员权限

    :param session: 数据库会话
    :param request: 创建请求
    :return: 创建结果
    """
    # 验证本地存储策略必须指定 server 路径
    if request.type == PolicyType.LOCAL:
        if not request.server:
            raise HTTPException(status_code=400, detail="本地存储策略必须指定 server 路径")

    # 检查策略名称是否已存在
    existing = await Policy.get(session, Policy.name == request.name)
    if existing:
        raise HTTPException(status_code=409, detail="策略名称已存在")

    # 创建策略对象
    policy = Policy(
        name=request.name,
        type=request.type,
        server=request.server,
        bucket_name=request.bucket_name,
        is_private=request.is_private,
        base_url=request.base_url,
        access_key=request.access_key,
        secret_key=request.secret_key,
        max_size=request.max_size,
        auto_rename=request.auto_rename,
        dir_name_rule=request.dir_name_rule,
        file_name_rule=request.file_name_rule,
        is_origin_link_enable=request.is_origin_link_enable,
    )

    # 对于本地存储策略，创建物理目录
    if policy.type == PolicyType.LOCAL:
        try:
            storage_service = LocalStorageService(policy)
            await storage_service.ensure_base_directory()
            l.info(f"已为本地存储策略 '{policy.name}' 创建目录: {policy.server}")
        except DirectoryCreationError as e:
            raise HTTPException(status_code=500, detail=f"创建存储目录失败: {e}")

    # 保存到数据库
    policy = await policy.save(session)

    return ResponseBase(data={
        "id": str(policy.id),
        "name": policy.name,
        "type": policy.type.value,
        "server": policy.server,
    })

@admin_policy_router.post(
    path='/cors',
    summary='创建跨域策略',
    description='Create CORS policy for S3 storage',
    dependencies=[Depends(AdminRequired)]
)
async def router_policy_add_cors() -> ResponseBase:
    """
    创建CORS配置（S3相关）。

    此端点用于S3存储的跨域配置。
    """
    # TODO: 实现S3 CORS配置
    raise HTTPException(status_code=501, detail="S3 CORS配置暂未实现")


@admin_policy_router.post(
    path='/scf',
    summary='创建COS回调函数',
    description='Create COS callback function',
    dependencies=[Depends(AdminRequired)]
)
async def router_policy_add_scf() -> ResponseBase:
    """
    创建COS回调函数。

    此端点用于腾讯云COS的云函数回调配置。
    """
    # TODO: 实现COS SCF配置
    raise HTTPException(status_code=501, detail="COS回调函数配置暂未实现")


@admin_policy_router.get(
    path='/{policy_id}/oauth',
    summary='获取 OneDrive OAuth URL',
    description='Get OneDrive OAuth URL',
    dependencies=[Depends(AdminRequired)]
)
async def router_policy_onddrive_oauth(
    session: SessionDep,
    policy_id: UUID,
) -> ResponseBase:
    """
    获取OneDrive OAuth授权URL。

    :param session: 数据库会话
    :param policy_id: 存储策略UUID
    :return: OAuth URL
    """
    policy = await Policy.get(session, Policy.id == policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="存储策略不存在")

    # TODO: 实现OneDrive OAuth
    raise HTTPException(status_code=501, detail="OneDrive OAuth暂未实现")


@admin_policy_router.get(
    path='/{policy_id}',
    summary='获取存储策略',
    description='Get storage policy by ID',
    dependencies=[Depends(AdminRequired)]
)
async def router_policy_get_policy(
    session: SessionDep,
    policy_id: UUID,
) -> ResponseBase:
    """
    获取存储策略详情。

    :param session: 数据库会话
    :param policy_id: 存储策略UUID
    :return: 策略详情
    """
    policy = await Policy.get(session, Policy.id == policy_id, load=Policy.options)
    if not policy:
        raise HTTPException(status_code=404, detail="存储策略不存在")

    # 获取使用此策略的用户组
    groups = await policy.awaitable_attrs.groups

    # 统计使用此策略的对象数量
    object_count = await Object.count(session, Object.policy_id == policy_id)

    return ResponseBase(data={
        "id": str(policy.id),
        "name": policy.name,
        "type": policy.type.value,
        "server": policy.server,
        "bucket_name": policy.bucket_name,
        "is_private": policy.is_private,
        "base_url": policy.base_url,
        "max_size": policy.max_size,
        "auto_rename": policy.auto_rename,
        "dir_name_rule": policy.dir_name_rule,
        "file_name_rule": policy.file_name_rule,
        "is_origin_link_enable": policy.is_origin_link_enable,
        "options": policy.options.model_dump() if policy.options else None,
        "groups": [{"id": str(g.id), "name": g.name} for g in groups],
        "object_count": object_count,
    })


@admin_policy_router.delete(
    path='/{policy_id}',
    summary='删除存储策略',
    description='Delete storage policy by ID',
    dependencies=[Depends(AdminRequired)]
)
async def router_policy_delete_policy(
    session: SessionDep,
    policy_id: UUID,
) -> ResponseBase:
    """
    删除存储策略。

    注意: 如果有文件使用此策略，会拒绝删除。

    :param session: 数据库会话
    :param policy_id: 存储策略UUID
    :return: 删除结果
    """
    policy = await Policy.get(session, Policy.id == policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="存储策略不存在")

    # 检查是否有文件使用此策略
    file_count = await Object.count(session, Object.policy_id == policy_id)
    if file_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"无法删除，还有 {file_count} 个文件使用此策略"
        )

    policy_name = policy.name
    await Policy.delete(session, policy)

    l.info(f"管理员删除了存储策略: {policy_name}")
    return ResponseBase(data={"deleted": True})


# ==================== 分享管理端点 ====================

@admin_share_router.get(
    path='/list',
    summary='获取分享列表',
    description='Get share list',
    dependencies=[Depends(AdminRequired)]
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
    dependencies=[Depends(AdminRequired)]
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
    dependencies=[Depends(AdminRequired)]
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


# ==================== 任务管理端点 ====================

@admin_task_router.get(
    path='/list',
    summary='获取任务列表',
    description='Get task list',
    dependencies=[Depends(AdminRequired)]
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
    dependencies=[Depends(AdminRequired)]
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
    dependencies=[Depends(AdminRequired)]
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


# ==================== 增值服务端点 ====================

@admin_vas_router.get(
    path='/list',
    summary='获取增值服务列表',
    description='Get VAS list (orders and storage packs)',
    dependencies=[Depends(AdminRequired)]
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
    dependencies=[Depends(AdminRequired)]
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
    dependencies=[Depends(AdminRequired)]
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