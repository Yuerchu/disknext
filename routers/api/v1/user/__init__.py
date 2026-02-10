from typing import Annotated, Literal
from uuid import UUID, uuid4

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from loguru import logger
from webauthn import generate_registration_options
from webauthn.helpers import options_to_json_dict

import service
import sqlmodels
from middleware.auth import auth_required
from middleware.dependencies import SessionDep
from utils import JWT, Password, http_exceptions
from .settings import user_settings_router

user_router = APIRouter(
    prefix="/user",
    tags=["user"],
)

user_router.include_router(user_settings_router)

@user_router.post(
    path='/session',
    summary='用户登录',
    description='User login endpoint. 当用户启用两步验证时，需要传入 otp 参数。',
)
async def router_user_session(
    session: SessionDep,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> sqlmodels.TokenResponse:
    """
    用户登录端点。

    根据 OAuth2.1 规范，使用 password grant type 进行登录。
    当用户启用两步验证时，需要在表单中传入 otp 参数（通过 scopes 字段传递）。

    OAuth2 scopes 字段格式: "otp:123456" 或直接传入验证码
    """
    email = form_data.username  # OAuth2 表单字段名为 username，实际传入的是 email
    password = form_data.password

    # 从 scopes 中提取 OTP 验证码（OAuth2.1 扩展方式）
    # scopes 格式可以是 ["otp:123456"] 或 ["123456"]
    otp_code: str | None = None
    for scope in form_data.scopes:
        if scope.startswith("otp:"):
            otp_code = scope[4:]
            break
        elif scope.isdigit() and len(scope) == 6:
            otp_code = scope
            break

    result = await service.user.login(
        session,
        sqlmodels.LoginRequest(
            email=email,
            password=password,
            two_fa_code=otp_code,
        ),
    )

    return result

@user_router.post(
    path='/session/refresh',
    summary="用刷新令牌刷新会话",
    description="Refresh the user session using a refresh token."
)
async def router_user_session_refresh(
    session: SessionDep,
    request: sqlmodels.RefreshTokenRequest,
) -> sqlmodels.TokenResponse:
    """
    使用 refresh_token 签发新的 access_token 和 refresh_token。

    流程：
    1. 解码 refresh_token JWT
    2. 验证 token_type 为 refresh
    3. 验证用户存在且状态正常
    4. 签发新的 access_token + refresh_token

    :param session: 数据库会话
    :param request: 刷新令牌请求
    :return: 新的 TokenResponse
    """

    try:
        payload = jwt.decode(request.refresh_token, JWT.SECRET_KEY, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        http_exceptions.raise_unauthorized("刷新令牌无效或已过期")

    # 验证是 refresh token
    if payload.get("token_type") != "refresh":
        http_exceptions.raise_unauthorized("非刷新令牌")

    user_id_str = payload.get("sub")
    if not user_id_str:
        http_exceptions.raise_unauthorized("令牌缺少用户标识")

    user_id = UUID(user_id_str)
    user = await sqlmodels.User.get(session, sqlmodels.User.id == user_id)
    if not user:
        http_exceptions.raise_unauthorized("用户不存在")

    if not user.status:
        http_exceptions.raise_forbidden("账户已被禁用")

    # 签发新令牌
    access_token = JWT.create_access_token(
        sub=user.id,
        jti=uuid4(),
    )
    refresh_token = JWT.create_refresh_token(
        sub=user.id,
        jti=uuid4(),
    )

    return sqlmodels.TokenResponse(
        access_token=access_token.access_token,
        access_expires=access_token.access_expires,
        refresh_token=refresh_token.refresh_token,
        refresh_expires=refresh_token.refresh_expires,
    )

@user_router.post(
    path='/',
    summary='用户注册',
    description='User registration endpoint.',
    status_code=204,
)
async def router_user_register(
    session: SessionDep,
    request: sqlmodels.RegisterRequest,
) -> None:
    """
    用户注册端点

    流程：
    1. 验证用户名唯一性
    2. 获取默认用户组
    3. 创建用户记录
    4. 创建用户根目录（name="/"）

    :param session: 数据库会话
    :param request: 注册请求
    :return: 注册结果
    :raises HTTPException 400: 用户名已存在
    :raises HTTPException 500: 默认用户组或存储策略不存在
    """
    # 1. 验证邮箱唯一性
    existing_user = await sqlmodels.User.get(
        session,
        sqlmodels.User.email == request.email
    )
    if existing_user:
        raise HTTPException(status_code=400, detail="邮箱已存在")

    # 2. 获取默认用户组（从设置中读取 UUID）
    default_group_setting: sqlmodels.Setting | None = await sqlmodels.Setting.get(
        session,
        (sqlmodels.Setting.type == sqlmodels.SettingsType.REGISTER) & (sqlmodels.Setting.name == "default_group")
    )
    if default_group_setting is None or not default_group_setting.value:
        logger.error("默认用户组不存在")
        http_exceptions.raise_internal_error()

    default_group_id = UUID(default_group_setting.value)
    default_group = await sqlmodels.Group.get(session, sqlmodels.Group.id == default_group_id)
    if not default_group:
        logger.error("默认用户组不存在")
        http_exceptions.raise_internal_error()

    # 3. 创建用户
    hashed_password = Password.hash(request.password)
    new_user = sqlmodels.User(
        email=request.email,
        password=hashed_password,
        group_id=default_group.id,
    )
    new_user_id = new_user.id
    await new_user.save(session)

    # 4. 创建用户根目录
    default_policy = await sqlmodels.Policy.get(session, sqlmodels.Policy.name == "本地存储")
    if not default_policy:
        logger.error("默认存储策略不存在")
        http_exceptions.raise_internal_error()

    await sqlmodels.Object(
        name="/",
        type=sqlmodels.ObjectType.FOLDER,
        owner_id=new_user_id,
        parent_id=None,
        policy_id=default_policy.id,
    ).save(session)

@user_router.post(
    path='/code',
    summary='发送验证码邮件',
    description='Send a verification code email.',
)
def router_user_email_code(
    reason: Literal['register', 'reset'] = 'register',
) -> sqlmodels.ResponseBase:
    """
    Send a verification code email.
    
    Returns:
        dict: A dictionary containing information about the password reset email.
    """
    http_exceptions.raise_not_implemented()

@user_router.get(
    path='/qq',
    summary='初始化QQ登录',
    description='Initialize QQ login for a user.',
)
def router_user_qq() -> sqlmodels.ResponseBase: 
    """
    Initialize QQ login for a user.
    
    Returns:
        dict: A dictionary containing QQ login initialization information.
    """
    http_exceptions.raise_not_implemented()

@user_router.get(
    path='authn/{username}',
    summary='WebAuthn登录初始化',
    description='Initialize WebAuthn login for a user.',
)
async def router_user_authn(username: str) -> sqlmodels.ResponseBase:
    
    http_exceptions.raise_not_implemented()

@user_router.post(
    path='authn/finish/{username}',
    summary='WebAuthn登录',
    description='Finish WebAuthn login for a user.',
)
def router_user_authn_finish(username: str) -> sqlmodels.ResponseBase:
    """
    Finish WebAuthn login for a user.
    
    Args:
        username (str): The username of the user.
    
    Returns:
        dict: A dictionary containing WebAuthn login information.
    """
    http_exceptions.raise_not_implemented()

@user_router.get(
    path='/profile/{id}',
    summary='获取用户主页展示用分享',
    description='Get user profile for display.',
)
def router_user_profile(id: str) -> sqlmodels.ResponseBase:
    """
    Get user profile for display.
    
    Args:
        id (str): The user ID.
    
    Returns:
        dict: A dictionary containing user profile information.
    """
    http_exceptions.raise_not_implemented()

@user_router.get(
    path='/avatar/{id}/{size}',
    summary='获取用户头像',
    description='Get user avatar by ID and size.',
)
def router_user_avatar(id: str, size: int = 128) -> sqlmodels.ResponseBase:
    """
    Get user avatar by ID and size.
    
    Args:
        id (str): The user ID.
        size (int): The size of the avatar image.
    
    Returns:
        str: A Base64 encoded string of the user avatar image.
    """
    http_exceptions.raise_not_implemented()

#####################
# 需要登录的接口
#####################

@user_router.get(
    path='/me',
    summary='获取用户信息',
    description='Get user information.',
    dependencies=[Depends(dependency=auth_required)],
    response_model=sqlmodels.UserResponse,
)
async def router_user_me(
    session: SessionDep,
    user: Annotated[sqlmodels.User, Depends(auth_required)],
) -> sqlmodels.UserResponse:
    """
    获取用户信息.

    :return: ResponseBase containing user information.
    :rtype: ResponseBase
    """
    # 加载 group 及其 options 关系
    group = await sqlmodels.Group.get(
        session,
        sqlmodels.Group.id == user.group_id,
        load=sqlmodels.Group.options
    )

    # 构建 GroupResponse
    group_response = group.to_response() if group else None

    # 异步加载 tags 关系
    user_tags = await user.awaitable_attrs.tags

    return sqlmodels.UserResponse(
        id=user.id,
        email=user.email,
        status=user.status,
        score=user.score,
        nickname=user.nickname,
        avatar=user.avatar,
        created_at=user.created_at,
        group=group_response,
        tags=[tag.name for tag in user_tags] if user_tags else [],
    )

@user_router.get(
    path='/storage',
    summary='存储信息',
    description='Get user storage information.',
    dependencies=[Depends(auth_required)],
)
async def router_user_storage(
    session: SessionDep,
    user: Annotated[sqlmodels.user.User, Depends(auth_required)],
) -> sqlmodels.UserStorageResponse:
    """
    获取用户存储空间信息。
    """
    # 获取用户组的基础存储容量
    group = await sqlmodels.Group.get(session, sqlmodels.Group.id == user.group_id)
    if not group:
        raise HTTPException(status_code=404, detail="用户组不存在")
    
    # [TODO] 总空间加上用户购买的额外空间
    
    total: int = group.max_storage
    used: int = user.storage
    free: int = max(0, total - used)

    return sqlmodels.UserStorageResponse(
        used=used,
        free=free,
        total=total,
    )

@user_router.put(
    path='/authn/start',
    summary='WebAuthn登录初始化',
    description='Initialize WebAuthn login for a user.',
    dependencies=[Depends(auth_required)],
)
async def router_user_authn_start(
    session: SessionDep,
    user: Annotated[sqlmodels.user.User, Depends(auth_required)],
) -> sqlmodels.ResponseBase:
    """
    Initialize WebAuthn login for a user.

    Returns:
        dict: A dictionary containing WebAuthn initialization information.
    """
    # TODO: 检查 WebAuthn 是否开启，用户是否有注册过 WebAuthn 设备等
    authn_setting = await sqlmodels.Setting.get(
        session,
        (sqlmodels.Setting.type == "authn") & (sqlmodels.Setting.name == "authn_enabled")
    )
    if not authn_setting or authn_setting.value != "1":
        raise HTTPException(status_code=400, detail="WebAuthn is not enabled")

    site_url_setting = await sqlmodels.Setting.get(
        session,
        (sqlmodels.Setting.type == "basic") & (sqlmodels.Setting.name == "siteURL")
    )
    site_title_setting = await sqlmodels.Setting.get(
        session,
        (sqlmodels.Setting.type == "basic") & (sqlmodels.Setting.name == "siteTitle")
    )

    options = generate_registration_options(
        rp_id=site_url_setting.value if site_url_setting else "",
        rp_name=site_title_setting.value if site_title_setting else "",
        user_name=user.email,
        user_display_name=user.nickname or user.email,
    )

    return sqlmodels.ResponseBase(data=options_to_json_dict(options))

@user_router.put(
    path='/authn/finish',
    summary='WebAuthn登录',
    description='Finish WebAuthn login for a user.',
    dependencies=[Depends(auth_required)],
)
def router_user_authn_finish() -> sqlmodels.ResponseBase:
    """
    Finish WebAuthn login for a user.
    
    Returns:
        dict: A dictionary containing WebAuthn login information.
    """
    http_exceptions.raise_not_implemented()