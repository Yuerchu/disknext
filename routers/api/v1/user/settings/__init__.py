from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

import sqlmodels
from middleware.auth import auth_required
from middleware.dependencies import SessionDep
from utils import JWT, Password, http_exceptions

user_settings_router = APIRouter(
    prefix='/settings',
    tags=["user", "user_settings"],
    dependencies=[Depends(auth_required)],
)


@user_settings_router.get(
    path='/policies',
    summary='获取用户可选存储策略',
    description='Get user selectable storage policies.',
)
def router_user_settings_policies() -> sqlmodels.ResponseBase:
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
def router_user_settings_nodes() -> sqlmodels.ResponseBase:
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
def router_user_settings_tasks() -> sqlmodels.ResponseBase:
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
)
def router_user_settings(
        user: Annotated[sqlmodels.user.User, Depends(auth_required)],
) -> sqlmodels.UserSettingResponse:
    """
    Get current user settings.

    Returns:
        dict: A dictionary containing the current user settings.
    """
    return sqlmodels.UserSettingResponse(
        id=user.id,
        email=user.email,
        nickname=user.nickname,
        created_at=user.created_at,
        group_name=user.group.name,
        language=user.language,
        timezone=user.timezone,
        group_expires=user.group_expires,
        two_factor=user.two_factor is not None,
    )


@user_settings_router.post(
    path='/avatar',
    summary='从文件上传头像',
    description='Upload user avatar from file.',
    dependencies=[Depends(auth_required)],
)
def router_user_settings_avatar() -> sqlmodels.ResponseBase:
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
def router_user_settings_avatar_gravatar() -> sqlmodels.ResponseBase:
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
def router_user_settings_patch(option: str) -> sqlmodels.ResponseBase:
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
    user: Annotated[sqlmodels.user.User, Depends(auth_required)],
) -> sqlmodels.ResponseBase:
    """
    Get two-factor authentication initialization information.

    Returns:
        dict: A dictionary containing two-factor authentication setup information.
    """

    return sqlmodels.ResponseBase(
        data=await Password.generate_totp(user.email)
    )


@user_settings_router.post(
    path='/2fa',
    summary='启用两步验证',
    description='Enable two-factor authentication.',
    dependencies=[Depends(auth_required)],
)
async def router_user_settings_2fa_enable(
    session: SessionDep,
    user: Annotated[sqlmodels.user.User, Depends(auth_required)],
    setup_token: str,
    code: str,
) -> sqlmodels.ResponseBase:
    """
    Enable two-factor authentication for the user.

    Returns:
        dict: A dictionary containing the result of enabling two-factor authentication.
    """

    serializer = URLSafeTimedSerializer(JWT.SECRET_KEY)

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

    return sqlmodels.ResponseBase(
        data={"message": "Two-factor authentication enabled successfully"}
    )