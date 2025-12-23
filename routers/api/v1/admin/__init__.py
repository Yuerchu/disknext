from fastapi import APIRouter, Depends, HTTPException
from loguru import logger as l
from sqlmodel import Field

from middleware.auth import AdminRequired
from middleware.dependencies import SessionDep
from models import Policy, PolicyOptions, PolicyType, User
from models.base import SQLModelBase
from models import ResponseBase
from models.user import UserPublic
from service.storage import DirectoryCreationError, LocalStorageService


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
def router_admin_update_settings() -> ResponseBase:
    """
    更新站点设置，包括站点名称、描述等。
    
    Returns:
        ResponseBase: 包含更新结果的响应模型。
    """
    pass

@admin_router.get(
    path='/settings',
    summary='获取设置',
    description='Get settings',
    dependencies=[Depends(AdminRequired)],
)
def router_admin_get_settings() -> ResponseBase:
    """
    获取站点设置，包括站点名称、描述等。
    
    Returns:
        ResponseBase: 包含站点设置的响应模型。
    """
    pass

@admin_group_router.get(
    path='/',
    summary='获取用户组列表',
    description='Get user group list',
    dependencies=[Depends(AdminRequired)],
)
def router_admin_get_groups() -> ResponseBase:
    """
    获取用户组列表，包括每个用户组的名称和权限信息。
    
    Returns:
        ResponseBase: 包含用户组列表的响应模型。
    """
    pass

@admin_group_router.get(
    path='/{group_id}',
    summary='获取用户组信息',
    description='Get user group information by ID',
    dependencies=[Depends(AdminRequired)],
)
def router_admin_get_group(group_id: int) -> ResponseBase:
    """
    根据用户组ID获取用户组信息，包括名称、权限等。
    
    Args:
        group_id (int): 用户组ID。
    
    Returns:
        ResponseBase: 包含用户组信息的响应模型。
    """
    pass

@admin_group_router.get(
    path='/list/{group_id}',
    summary='获取用户组成员列表',
    description='Get user group member list by group ID',
    dependencies=[Depends(AdminRequired)],
)
def router_admin_get_group_members(
    group_id: int,
    page: int = 1,
    page_size: int = 20
) -> ResponseBase:
    """
    根据用户组ID获取用户组成员列表。
    
    Args:
        group_id (int): 用户组ID。
        page (int): 页码，默认为1。
        page_size (int, optional): 每页显示的成员数量，默认为20。
    
    Returns:
        ResponseBase: 包含用户组成员列表的响应模型。
    """
    pass

@admin_group_router.post(
    path='/',
    summary='创建用户组',
    description='Create a new user group',
    dependencies=[Depends(AdminRequired)],
)
def router_admin_create_group() -> ResponseBase:
    """
    创建一个新的用户组，设置名称和权限等信息。
    
    Returns:
        ResponseBase: 包含创建结果的响应模型。
    """
    pass

@admin_group_router.patch(
    path='/{group_id}',
    summary='更新用户组信息',
    description='Update user group information by ID',
    dependencies=[Depends(AdminRequired)],
)
def router_admin_update_group(group_id: int) -> ResponseBase:
    """
    根据用户组ID更新用户组信息，包括名称、权限等。
    
    Args:
        group_id (int): 用户组ID。
    
    Returns:
        ResponseBase: 包含更新结果的响应模型。
    """
    pass

@admin_group_router.delete(
    path='/{group_id}',
    summary='删除用户组',
    description='Delete user group by ID',
    dependencies=[Depends(AdminRequired)],
)
def router_admin_delete_group(group_id: int) -> ResponseBase:
    """
    根据用户组ID删除用户组。
    
    Args:
        group_id (int): 用户组ID。
    
    Returns:
        ResponseBase: 包含删除结果的响应模型。
    """
    pass

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
def router_admin_update_user(user_id: int) -> ResponseBase:
    """
    根据用户ID更新用户信息，包括用户名、邮箱等。
    
    Args:
        user_id (int): 用户ID。
    
    Returns:
        ResponseBase: 包含更新结果的响应模型。
    """
    pass

@admin_user_router.delete(
    path='/{user_id}',
    summary='删除用户',
    description='Delete user by ID',
    dependencies=[Depends(AdminRequired)],
)
def router_admin_delete_user(user_id: int) -> ResponseBase:
    """
    根据用户ID删除用户。
    
    Args:
        user_id (int): 用户ID。
    
    Returns:
        ResponseBase: 包含删除结果的响应模型。
    """
    pass

@admin_user_router.post(
    path='/calibrate/{user_id}',
    summary='校准用户存储容量',
    description='Calibrate the user storage.',
    dependencies=[Depends(AdminRequired)]
)
def router_admin_calibrate_storage():
    pass

@admin_file_router.get(
    path='/list',
    summary='获取文件',
    description='Get file list',
    dependencies=[Depends(AdminRequired)],
)
def router_admin_get_file_list() -> ResponseBase:
    """
    获取文件列表，包括文件名称、大小、上传时间等。
    
    Returns:
        ResponseBase: 包含文件列表的响应模型。
    """
    pass

@admin_file_router.get(
    path='/preview/{file_id}',
    summary='预览文件',
    description='Preview file by ID',
    dependencies=[Depends(AdminRequired)],
)
def router_admin_preview_file(file_id: int) -> ResponseBase:
    """
    根据文件ID预览文件内容。
    
    Args:
        file_id (int): 文件ID。
    
    Returns:
        ResponseBase: 包含文件预览内容的响应模型。
    """
    pass

@admin_file_router.patch(
    path='/ban/{file_id}',
    summary='封禁文件',
    description='Ban the file, user can\'t open, copy, move, download or share this file if administrator ban.',
    dependencies=[Depends(AdminRequired)],
)
def router_admin_ban_file(file_id: int) -> ResponseBase:
    """
    根据文件ID封禁文件。
    
    如果管理员封禁了某个文件，用户将无法打开、复制或移动、下载或分享此文件。
    
    Args:
        file_id (int): 文件ID。
    
    Returns:
        ResponseBase: 包含删除结果的响应模型。
    """
    pass

@admin_file_router.delete(
    path='/{file_id}',
    summary='删除文件',
    description='Delete file by ID',
    dependencies=[Depends(AdminRequired)],
)
def router_admin_delete_file(file_id: int) -> ResponseBase:
    """
    根据文件ID删除文件。
    
    Args:
        file_id (int): 文件ID。
    
    Returns:
        ResponseBase: 包含删除结果的响应模型。
    """
    pass

@admin_aria2_router.post(
    path='/test',
    summary='测试连接配置',
    description='',
    dependencies=[Depends(AdminRequired)]
)
def router_admin_aira2_test() -> ResponseBase:
    pass

@admin_policy_router.get(
    path='/list',
    summary='列出存储策略',
    description='',
    dependencies=[Depends(AdminRequired)]
)
def router_policy_list() -> ResponseBase:
    pass

@admin_policy_router.post(
    path='/test/path',
    summary='测试本地路径可用性',
    description='',
    dependencies=[Depends(AdminRequired)]
)
def router_policy_test_path() -> ResponseBase:
    pass

@admin_policy_router.post(
    path='/test/slave',
    summary='测试从机通信',
    description='',
    dependencies=[Depends(AdminRequired)]
)
def router_policy_test_slave() -> ResponseBase:
    pass

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
    description='',
    dependencies=[Depends(AdminRequired)]
)
def router_policy_add_cors() -> ResponseBase:
    pass

@admin_policy_router.post(
    path='/scf',
    summary='创建COS回调函数',
    description='',
    dependencies=[Depends(AdminRequired)]
)
def router_policy_add_scf() -> ResponseBase:
    pass
    
@admin_policy_router.get(
    path='/{id}/oauth',
    summary='获取 OneDrive OAuth URL',
    description='',
    dependencies=[Depends(AdminRequired)]
)
def router_policy_onddrive_oauth() -> ResponseBase:
    pass

@admin_policy_router.get(
    path='/{id}',
    summary='获取存储策略',
    description='',
    dependencies=[Depends(AdminRequired)]
)
def router_policy_get_policy() -> ResponseBase:
    pass

@admin_policy_router.delete(
    path='/{id}',
    summary='删除存储策略',
    description='',
    dependencies=[Depends(AdminRequired)]
)
def router_policy_delete_policy() -> ResponseBase:
    pass