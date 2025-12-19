from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import and_
from webauthn import generate_registration_options
from webauthn.helpers import options_to_json_dict
import pyotp
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

import models
import service
from middleware.auth import AuthRequired
from middleware.dependencies import SessionDep
from pkg.JWT.JWT import SECRET_KEY
from pkg import Password

user_router = APIRouter(
    prefix="/user",
    tags=["user"],
)

user_settings_router = APIRouter(
    prefix='/user/settings',
    tags=["user", "user_settings"],
    dependencies=[Depends(AuthRequired)],
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

    :raises HTTPException 401: 用户名或密码错误
    :raises HTTPException 403: 用户账号被封禁或未完成注册
    :raises HTTPException 428: 需要两步验证但未提供验证码
    :raises HTTPException 400: 两步验证码无效
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

    result = await service.user.Login(
        session,
        models.LoginRequest(
            username=username,
            password=password,
            two_fa_code=otp_code,
        ),
    )

    if isinstance(result, models.TokenResponse):
        return result
    elif result is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    elif result is False:
        raise HTTPException(status_code=403, detail="User account is banned or not fully registered")
    elif result == "2fa_required":
        raise HTTPException(
            status_code=428,
            detail="Two-factor authentication required",
            headers={"X-2FA-Required": "true"},
        )
    elif result == "2fa_invalid":
        raise HTTPException(status_code=400, detail="Invalid two-factor authentication code")
    else:
        raise HTTPException(status_code=500, detail="Internal server error during login")

@user_router.post(
    path='/',
    summary='用户注册',
    description='User registration endpoint.',
)
def router_user_register() -> models.response.ResponseModel:
    """
    User registration endpoint.
    
    Returns:
        dict: A dictionary containing user registration information.
    """
    pass

@user_router.post(
    path='/code',
    summary='发送验证码邮件',
    description='Send a verification code email.',
)
def router_user_email_code(
    reason: Literal['register', 'reset'] = 'register',
) -> models.response.ResponseModel:
    """
    Send a verification code email.
    
    Returns:
        dict: A dictionary containing information about the password reset email.
    """
    pass

@user_router.get(
    path='/qq',
    summary='初始化QQ登录',
    description='Initialize QQ login for a user.',
)
def router_user_qq() -> models.response.ResponseModel: 
    """
    Initialize QQ login for a user.
    
    Returns:
        dict: A dictionary containing QQ login initialization information.
    """
    pass

@user_router.get(
    path='authn/{username}',
    summary='WebAuthn登录初始化',
    description='Initialize WebAuthn login for a user.',
)
async def router_user_authn(username: str) -> models.response.ResponseModel:
    
    pass

@user_router.post(
    path='authn/finish/{username}',
    summary='WebAuthn登录',
    description='Finish WebAuthn login for a user.',
)
def router_user_authn_finish(username: str) -> models.response.ResponseModel:
    """
    Finish WebAuthn login for a user.
    
    Args:
        username (str): The username of the user.
    
    Returns:
        dict: A dictionary containing WebAuthn login information.
    """
    pass

@user_router.get(
    path='/profile/{id}',
    summary='获取用户主页展示用分享',
    description='Get user profile for display.',
)
def router_user_profile(id: str) -> models.response.ResponseModel:
    """
    Get user profile for display.
    
    Args:
        id (str): The user ID.
    
    Returns:
        dict: A dictionary containing user profile information.
    """
    pass

@user_router.get(
    path='/avatar/{id}/{size}',
    summary='获取用户头像',
    description='Get user avatar by ID and size.',
)
def router_user_avatar(id: str, size: int = 128) -> models.response.ResponseModel:
    """
    Get user avatar by ID and size.
    
    Args:
        id (str): The user ID.
        size (int): The size of the avatar image.
    
    Returns:
        str: A Base64 encoded string of the user avatar image.
    """
    pass

#####################
# 需要登录的接口
#####################

@user_router.get(
    path='/me',
    summary='获取用户信息',
    description='Get user information.',
    dependencies=[Depends(dependency=AuthRequired)],
    response_model=models.response.ResponseModel,
)
async def router_user_me(
    session: SessionDep,
    user: Annotated[models.User, Depends(AuthRequired)],
) -> models.response.ResponseModel:
    """
    获取用户信息.

    :return: response.ResponseModel containing user information.
    :rtype: response.ResponseModel
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

    return models.response.ResponseModel(data=user_response.model_dump())

@user_router.get(
    path='/storage',
    summary='存储信息',
    description='Get user storage information.',
    dependencies=[Depends(AuthRequired)],
)
async def router_user_storage(
    session: SessionDep,
    user: Annotated[models.user.User, Depends(AuthRequired)],
) -> models.response.ResponseModel:
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

    return models.response.ResponseModel(
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
    dependencies=[Depends(AuthRequired)],
)
async def router_user_authn_start(
    session: SessionDep,
    user: Annotated[models.user.User, Depends(AuthRequired)],
) -> models.response.ResponseModel:
    """
    Initialize WebAuthn login for a user.

    Returns:
        dict: A dictionary containing WebAuthn initialization information.
    """
    # TODO: 检查 WebAuthn 是否开启，用户是否有注册过 WebAuthn 设备等
    authn_setting = await models.Setting.get(
        session,
        and_(models.Setting.type == "authn", models.Setting.name == "authn_enabled")
    )
    if not authn_setting or authn_setting.value != "1":
        raise HTTPException(status_code=400, detail="WebAuthn is not enabled")

    site_url_setting = await models.Setting.get(
        session,
        and_(models.Setting.type == "basic", models.Setting.name == "siteURL")
    )
    site_title_setting = await models.Setting.get(
        session,
        and_(models.Setting.type == "basic", models.Setting.name == "siteTitle")
    )

    options = generate_registration_options(
        rp_id=site_url_setting.value if site_url_setting else "",
        rp_name=site_title_setting.value if site_title_setting else "",
        user_name=user.username,
        user_display_name=user.nick or user.username,
    )

    return models.response.ResponseModel(data=options_to_json_dict(options))

@user_router.put(
    path='/authn/finish',
    summary='WebAuthn登录',
    description='Finish WebAuthn login for a user.',
    dependencies=[Depends(AuthRequired)],
)
def router_user_authn_finish() -> models.response.ResponseModel:
    """
    Finish WebAuthn login for a user.
    
    Returns:
        dict: A dictionary containing WebAuthn login information.
    """
    pass

@user_settings_router.get(
    path='/policies',
    summary='获取用户可选存储策略',
    description='Get user selectable storage policies.',
)
def router_user_settings_policies() -> models.response.ResponseModel:
    """
    Get user selectable storage policies.
    
    Returns:
        dict: A dictionary containing available storage policies for the user.
    """
    pass

@user_settings_router.get(
    path='/nodes',
    summary='获取用户可选节点',
    description='Get user selectable nodes.',
    dependencies=[Depends(AuthRequired)],
)
def router_user_settings_nodes() -> models.response.ResponseModel:
    """
    Get user selectable nodes.
    
    Returns:
        dict: A dictionary containing available nodes for the user.
    """
    pass

@user_settings_router.get(
    path='/tasks',
    summary='任务队列',
    description='Get user task queue.',
    dependencies=[Depends(AuthRequired)],
)
def router_user_settings_tasks() -> models.response.ResponseModel:
    """
    Get user task queue.
    
    Returns:
        dict: A dictionary containing the user's task queue information.
    """
    pass

@user_settings_router.get(
    path='/',
    summary='获取当前用户设定',
    description='Get current user settings.',
    dependencies=[Depends(AuthRequired)],
)
def router_user_settings() -> models.response.ResponseModel:
    """
    Get current user settings.
    
    Returns:
        dict: A dictionary containing the current user settings.
    """
    return models.response.ResponseModel(data=models.UserSettingResponse().model_dump())

@user_settings_router.post(
    path='/avatar',
    summary='从文件上传头像',
    description='Upload user avatar from file.',
    dependencies=[Depends(AuthRequired)],
)
def router_user_settings_avatar() -> models.response.ResponseModel:
    """
    Upload user avatar from file.
    
    Returns:
        dict: A dictionary containing the result of the avatar upload.
    """
    pass

@user_settings_router.put(
    path='/avatar',
    summary='设定为Gravatar头像',
    description='Set user avatar to Gravatar.',
    dependencies=[Depends(AuthRequired)],
)
def router_user_settings_avatar_gravatar() -> models.response.ResponseModel:
    """
    Set user avatar to Gravatar.
    
    Returns:
        dict: A dictionary containing the result of setting the Gravatar avatar.
    """
    pass

@user_settings_router.patch(
    path='/{option}',
    summary='更新用户设定',
    description='Update user settings.',
    dependencies=[Depends(AuthRequired)],
)
def router_user_settings_patch(option: str) -> models.response.ResponseModel:
    """
    Update user settings.
    
    Args:
        option (str): The setting option to update.
    
    Returns:
        dict: A dictionary containing the result of the settings update.
    """
    pass

@user_settings_router.get(
    path='/2fa',
    summary='获取两步验证初始化信息',
    description='Get two-factor authentication initialization information.',
    dependencies=[Depends(AuthRequired)],
)
async def router_user_settings_2fa(
    user: Annotated[models.user.User, Depends(AuthRequired)],
) -> models.response.ResponseModel:
    """
    Get two-factor authentication initialization information.
    
    Returns:
        dict: A dictionary containing two-factor authentication setup information.
    """

    return models.response.ResponseModel(
        data=await Password.generate_totp(user.username)
    )

@user_settings_router.post(
    path='/2fa',
    summary='启用两步验证',
    description='Enable two-factor authentication.',
    dependencies=[Depends(AuthRequired)],
)
async def router_user_settings_2fa_enable(
    session: SessionDep,
    user: Annotated[models.user.User, Depends(AuthRequired)],
    setup_token: str,
    code: str,
) -> models.response.ResponseModel:
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

    return models.response.ResponseModel(
        data={"message": "Two-factor authentication enabled successfully"}
    )