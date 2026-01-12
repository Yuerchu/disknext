from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from webauthn import generate_registration_options
from webauthn.helpers import options_to_json_dict
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from loguru import logger

import models
import service
from middleware.auth import auth_required
from middleware.dependencies import SessionDep
from utils.JWT import SECRET_KEY
from utils import Password, http_exceptions

user_router = APIRouter(
    prefix="/user",
    tags=["user"],
)

user_settings_router = APIRouter(
    prefix='/user/settings',
    tags=["user", "user_settings"],
    dependencies=[Depends(auth_required)],
)

@user_router.post(
    path='/session',
    summary='用户登录',
    description='User login endpoint. 当用户启用两步验证时，需要传入 otp 参数。',
)
async def router_user_session(
    session: SessionDep,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> models.TokenResponse:
    """
    用户登录端点。

    根据 OAuth2.1 规范，使用 password grant type 进行登录。
    当用户启用两步验证时，需要在表单中传入 otp 参数（通过 scopes 字段传递）。

    OAuth2 scopes 字段格式: "otp:123456" 或直接传入验证码
    """
    username = form_data.username
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
        models.LoginRequest(
            username=username,
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
    request, # RefreshTokenRequest
) -> models.TokenResponse:
    http_exceptions.raise_not_implemented()

@user_router.post(
    path='/',
    summary='用户注册',
    description='User registration endpoint.',
)
async def router_user_register(
    session: SessionDep,
    request: models.RegisterRequest,
) -> models.ResponseBase:
    """
    用户注册端点

    流程：
    1. 验证用户名唯一性
    2. 获取默认用户组
    3. 创建用户记录
    4. 创建以用户名命名的根目录

    :param session: 数据库会话
    :param request: 注册请求
    :return: 注册结果
    :raises HTTPException 400: 用户名已存在
    :raises HTTPException 500: 默认用户组或存储策略不存在
    """
    # 1. 验证用户名唯一性
    existing_user = await models.User.get(
        session,
        models.User.username == request.username
    )
    if existing_user:
        raise HTTPException(status_code=400, detail="用户名已存在")

    # 2. 获取默认用户组（从设置中读取 UUID）
    default_group_setting: models.Setting | None = await models.Setting.get(
        session,
        (models.Setting.type == models.SettingsType.REGISTER) & (models.Setting.name == "default_group")
    )
    if default_group_setting is None or not default_group_setting.value:
        logger.error("默认用户组不存在")
        http_exceptions.raise_internal_error()

    default_group_id = UUID(default_group_setting.value)
    default_group = await models.Group.get(session, models.Group.id == default_group_id)
    if not default_group:
        logger.error("默认用户组不存在")
        http_exceptions.raise_internal_error()

    # 3. 创建用户
    hashed_password = Password.hash(request.password)
    new_user = models.User(
        username=request.username,
        password=hashed_password,
        group_id=default_group.id,
    )
    new_user_id = new_user.id  # 在 save 前保存 UUID
    new_user_username = new_user.username
    await new_user.save(session)

    # 4. 创建以用户名命名的根目录
    default_policy = await models.Policy.get(session, models.Policy.name == "本地存储")
    if not default_policy:
        logger.error("默认存储策略不存在")
        http_exceptions.raise_internal_error()

    await models.Object(
        name=new_user_username,
        type=models.ObjectType.FOLDER,
        owner_id=new_user_id,
        parent_id=None,
        policy_id=default_policy.id,
    ).save(session)

    return models.ResponseBase(
        data={
            "user_id": new_user_id,
            "username": new_user_username,
        },
        msg="注册成功",
    )

@user_router.post(
    path='/code',
    summary='发送验证码邮件',
    description='Send a verification code email.',
)
def router_user_email_code(
    reason: Literal['register', 'reset'] = 'register',
) -> models.ResponseBase:
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
def router_user_qq() -> models.ResponseBase: 
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
async def router_user_authn(username: str) -> models.ResponseBase:
    
    http_exceptions.raise_not_implemented()

@user_router.post(
    path='authn/finish/{username}',
    summary='WebAuthn登录',
    description='Finish WebAuthn login for a user.',
)
def router_user_authn_finish(username: str) -> models.ResponseBase:
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
def router_user_profile(id: str) -> models.ResponseBase:
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
def router_user_avatar(id: str, size: int = 128) -> models.ResponseBase:
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
    response_model=models.ResponseBase,
)
async def router_user_me(
    session: SessionDep,
    user: Annotated[models.User, Depends(auth_required)],
) -> models.ResponseBase:
    """
    获取用户信息.

    :return: ResponseBase containing user information.
    :rtype: ResponseBase
    """
    # 加载 group 及其 options 关系
    group = await models.Group.get(
        session,
        models.Group.id == user.group_id,
        load=models.Group.options
    )

    # 构建 GroupResponse
    group_response = group.to_response() if group else None

    # 异步加载 tags 关系
    user_tags = await user.awaitable_attrs.tags

    user_response = models.UserResponse(
        id=user.id,
        username=user.username,
        status=user.status,
        score=user.score,
        nickname=user.nickname,
        avatar=user.avatar,
        created_at=user.created_at,
        group=group_response,
        tags=[tag.name for tag in user_tags] if user_tags else [],
    )

    return models.ResponseBase(data=user_response.model_dump())

@user_router.get(
    path='/storage',
    summary='存储信息',
    description='Get user storage information.',
    dependencies=[Depends(auth_required)],
)
async def router_user_storage(
    session: SessionDep,
    user: Annotated[models.user.User, Depends(auth_required)],
) -> models.ResponseBase:
    """
    获取用户存储空间信息。

    返回值：
        - used: 已使用空间（字节）
        - free: 剩余空间（字节）
        - total: 总容量（字节）= 用户组容量
    """
    # 获取用户组的基础存储容量
    group = await models.Group.get(session, models.Group.id == user.group_id)
    if not group:
        raise HTTPException(status_code=500, detail="用户组不存在")
    total: int = group.max_storage
    used: int = user.storage
    free: int = max(0, total - used)

    return models.ResponseBase(
        data={
            "used": used,
            "free": free,
            "total": total,
        }
    )

@user_router.put(
    path='/authn/start',
    summary='WebAuthn登录初始化',
    description='Initialize WebAuthn login for a user.',
    dependencies=[Depends(auth_required)],
)
async def router_user_authn_start(
    session: SessionDep,
    user: Annotated[models.user.User, Depends(auth_required)],
) -> models.ResponseBase:
    """
    Initialize WebAuthn login for a user.

    Returns:
        dict: A dictionary containing WebAuthn initialization information.
    """
    # TODO: 检查 WebAuthn 是否开启，用户是否有注册过 WebAuthn 设备等
    authn_setting = await models.Setting.get(
        session,
        (models.Setting.type == "authn") & (models.Setting.name == "authn_enabled")
    )
    if not authn_setting or authn_setting.value != "1":
        raise HTTPException(status_code=400, detail="WebAuthn is not enabled")

    site_url_setting = await models.Setting.get(
        session,
        (models.Setting.type == "basic") & (models.Setting.name == "siteURL")
    )
    site_title_setting = await models.Setting.get(
        session,
        (models.Setting.type == "basic") & (models.Setting.name == "siteTitle")
    )

    options = generate_registration_options(
        rp_id=site_url_setting.value if site_url_setting else "",
        rp_name=site_title_setting.value if site_title_setting else "",
        user_name=user.username,
        user_display_name=user.nick or user.username,
    )

    return models.ResponseBase(data=options_to_json_dict(options))

@user_router.put(
    path='/authn/finish',
    summary='WebAuthn登录',
    description='Finish WebAuthn login for a user.',
    dependencies=[Depends(auth_required)],
)
def router_user_authn_finish() -> models.ResponseBase:
    """
    Finish WebAuthn login for a user.
    
    Returns:
        dict: A dictionary containing WebAuthn login information.
    """
    http_exceptions.raise_not_implemented()

@user_settings_router.get(
    path='/policies',
    summary='获取用户可选存储策略',
    description='Get user selectable storage policies.',
)
def router_user_settings_policies() -> models.ResponseBase:
    """
    Get user selectable storage policies.
    
    Returns:
        dict: A dictionary containing available storage policies for the user.
    """
    http_exceptions.raise_not_implemented()

@user_settings_router.get(
    path='/nodes',
    summary='获取用户可选节点',
    description='Get user selectable nodes.',
    dependencies=[Depends(auth_required)],
)
def router_user_settings_nodes() -> models.ResponseBase:
    """
    Get user selectable nodes.
    
    Returns:
        dict: A dictionary containing available nodes for the user.
    """
    http_exceptions.raise_not_implemented()

@user_settings_router.get(
    path='/tasks',
    summary='任务队列',
    description='Get user task queue.',
    dependencies=[Depends(auth_required)],
)
def router_user_settings_tasks() -> models.ResponseBase:
    """
    Get user task queue.
    
    Returns:
        dict: A dictionary containing the user's task queue information.
    """
    http_exceptions.raise_not_implemented()

@user_settings_router.get(
    path='/',
    summary='获取当前用户设定',
    description='Get current user settings.',
    dependencies=[Depends(auth_required)],
)
def router_user_settings() -> models.ResponseBase:
    """
    Get current user settings.
    
    Returns:
        dict: A dictionary containing the current user settings.
    """
    return models.ResponseBase(data=models.UserSettingResponse().model_dump())

@user_settings_router.post(
    path='/avatar',
    summary='从文件上传头像',
    description='Upload user avatar from file.',
    dependencies=[Depends(auth_required)],
)
def router_user_settings_avatar() -> models.ResponseBase:
    """
    Upload user avatar from file.
    
    Returns:
        dict: A dictionary containing the result of the avatar upload.
    """
    http_exceptions.raise_not_implemented()

@user_settings_router.put(
    path='/avatar',
    summary='设定为Gravatar头像',
    description='Set user avatar to Gravatar.',
    dependencies=[Depends(auth_required)],
)
def router_user_settings_avatar_gravatar() -> models.ResponseBase:
    """
    Set user avatar to Gravatar.
    
    Returns:
        dict: A dictionary containing the result of setting the Gravatar avatar.
    """
    http_exceptions.raise_not_implemented()

@user_settings_router.patch(
    path='/{option}',
    summary='更新用户设定',
    description='Update user settings.',
    dependencies=[Depends(auth_required)],
)
def router_user_settings_patch(option: str) -> models.ResponseBase:
    """
    Update user settings.
    
    Args:
        option (str): The setting option to update.
    
    Returns:
        dict: A dictionary containing the result of the settings update.
    """
    http_exceptions.raise_not_implemented()

@user_settings_router.get(
    path='/2fa',
    summary='获取两步验证初始化信息',
    description='Get two-factor authentication initialization information.',
    dependencies=[Depends(auth_required)],
)
async def router_user_settings_2fa(
    user: Annotated[models.user.User, Depends(auth_required)],
) -> models.ResponseBase:
    """
    Get two-factor authentication initialization information.
    
    Returns:
        dict: A dictionary containing two-factor authentication setup information.
    """

    return models.ResponseBase(
        data=await Password.generate_totp(user.username)
    )

@user_settings_router.post(
    path='/2fa',
    summary='启用两步验证',
    description='Enable two-factor authentication.',
    dependencies=[Depends(auth_required)],
)
async def router_user_settings_2fa_enable(
    session: SessionDep,
    user: Annotated[models.user.User, Depends(auth_required)],
    setup_token: str,
    code: str,
) -> models.ResponseBase:
    """
    Enable two-factor authentication for the user.
    
    Returns:
        dict: A dictionary containing the result of enabling two-factor authentication.
    """

    serializer = URLSafeTimedSerializer(SECRET_KEY)

    try:
        # 1. 解包 Token，设置有效期（例如 600秒）
        secret = serializer.loads(setup_token, salt="2fa-setup-salt", max_age=600)
    except SignatureExpired:
        raise HTTPException(status_code=400, detail="Setup session expired")
    except BadSignature:
        raise HTTPException(status_code=400, detail="Invalid token")

    # 2. 验证用户输入的 6 位验证码
    if not Password.verify_totp(secret, code):
        raise HTTPException(status_code=400, detail="Invalid OTP code")

    # 3. 将 secret 存储到用户的数据库记录中，启用 2FA
    user.two_factor = secret
    user = await user.save(session)

    return models.ResponseBase(
        data={"message": "Two-factor authentication enabled successfully"}
    )