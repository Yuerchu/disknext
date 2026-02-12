from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

import sqlmodels
from middleware.auth import auth_required
from middleware.dependencies import SessionDep
from sqlmodels import (
    BUILTIN_DEFAULT_COLORS, ThemePreset, UserThemeUpdateRequest,
    SettingOption, UserSettingUpdateRequest,
)
from sqlmodels.color import ThemeColorsBase
from utils import JWT, Password, http_exceptions
from utils.password.pwd import PasswordStatus, TwoFactorResponse, TwoFactorVerifyRequest

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
async def router_user_settings(
        session: SessionDep,
        user: Annotated[sqlmodels.user.User, Depends(auth_required)],
) -> sqlmodels.UserSettingResponse:
    """
    获取当前用户设定

    主题颜色合并策略：
    1. 用户有颜色快照（7个字段均有值）→ 直接使用快照
    2. 否则查找默认预设 → 使用默认预设颜色
    3. 无默认预设 → 使用内置默认值
    """
    # 计算主题颜色
    has_snapshot = all([
        user.color_primary, user.color_secondary, user.color_success,
        user.color_info, user.color_warning, user.color_error, user.color_neutral,
    ])
    if has_snapshot:
        theme_colors = ThemeColorsBase(
            primary=user.color_primary,
            secondary=user.color_secondary,
            success=user.color_success,
            info=user.color_info,
            warning=user.color_warning,
            error=user.color_error,
            neutral=user.color_neutral,
        )
    else:
        default_preset: ThemePreset | None = await ThemePreset.get(
            session, ThemePreset.is_default == True  # noqa: E712
        )
        if default_preset:
            theme_colors = ThemeColorsBase(
                primary=default_preset.primary,
                secondary=default_preset.secondary,
                success=default_preset.success,
                info=default_preset.info,
                warning=default_preset.warning,
                error=default_preset.error,
                neutral=default_preset.neutral,
            )
        else:
            theme_colors = BUILTIN_DEFAULT_COLORS

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
        theme_preset_id=user.theme_preset_id,
        theme_colors=theme_colors,
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
    status_code=204,
)
def router_user_settings_avatar_gravatar() -> None:
    """
    Set user avatar to Gravatar.

    Returns:
        dict: A dictionary containing the result of setting the Gravatar avatar.
    """
    http_exceptions.raise_not_implemented()


@user_settings_router.patch(
    path='/theme',
    summary='更新用户主题设置',
    status_code=status.HTTP_204_NO_CONTENT,
)
async def router_user_settings_theme(
        session: SessionDep,
        user: Annotated[sqlmodels.user.User, Depends(auth_required)],
        request: UserThemeUpdateRequest,
) -> None:
    """
    更新用户主题设置

    请求体（均可选）：
    - theme_preset_id: 主题预设UUID
    - theme_colors: 颜色配置对象（写入颜色快照）

    错误处理：
    - 404: 指定的主题预设不存在
    """
    # 验证 preset_id 存在性
    if request.theme_preset_id is not None:
        preset: ThemePreset | None = await ThemePreset.get(
            session, ThemePreset.id == request.theme_preset_id
        )
        if not preset:
            http_exceptions.raise_not_found("主题预设不存在")
    user.theme_preset_id = request.theme_preset_id

    # 将颜色解构到快照列
    if request.theme_colors is not None:
        user.color_primary = request.theme_colors.primary
        user.color_secondary = request.theme_colors.secondary
        user.color_success = request.theme_colors.success
        user.color_info = request.theme_colors.info
        user.color_warning = request.theme_colors.warning
        user.color_error = request.theme_colors.error
        user.color_neutral = request.theme_colors.neutral

    await user.save(session)


@user_settings_router.patch(
    path='/{option}',
    summary='更新用户设定',
    status_code=status.HTTP_204_NO_CONTENT,
)
async def router_user_settings_patch(
        session: SessionDep,
        user: Annotated[sqlmodels.user.User, Depends(auth_required)],
        option: SettingOption,
        request: UserSettingUpdateRequest,
) -> None:
    """
    更新单个用户设置项

    路径参数：
    - option: 设置项名称（nickname / language / timezone）

    请求体：
    - 包含与 option 同名的字段及其新值

    错误处理：
    - 422: 无效的 option 或字段值不符合约束
    - 400: 必填字段值缺失
    """
    value = getattr(request, option.value)

    # language / timezone 不允许设为 null
    if value is None and option != SettingOption.NICKNAME:
        http_exceptions.raise_bad_request(f"设置项 {option.value} 不允许为空")

    setattr(user, option.value, value)
    await user.save(session)


@user_settings_router.get(
    path='/2fa',
    summary='获取两步验证初始化信息',
    description='Get two-factor authentication initialization information.',
    dependencies=[Depends(auth_required)],
)
async def router_user_settings_2fa(
    user: Annotated[sqlmodels.user.User, Depends(auth_required)],
) -> TwoFactorResponse:
    """
    获取两步验证初始化信息

    返回 setup_token（用于后续验证请求）和 uri（用于生成二维码）。
    """
    return await Password.generate_totp(name=user.email)


@user_settings_router.post(
    path='/2fa',
    summary='启用两步验证',
    description='Enable two-factor authentication.',
    dependencies=[Depends(auth_required)],
    status_code=204,
)
async def router_user_settings_2fa_enable(
    session: SessionDep,
    user: Annotated[sqlmodels.user.User, Depends(auth_required)],
    request: TwoFactorVerifyRequest,
) -> None:
    """
    启用两步验证

    请求体包含 setup_token（GET /2fa 返回的令牌）和 code（6 位验证码）。
    """
    serializer = URLSafeTimedSerializer(JWT.SECRET_KEY)

    try:
        secret = serializer.loads(request.setup_token, salt="2fa-setup-salt", max_age=600)
    except SignatureExpired:
        raise HTTPException(status_code=400, detail="Setup session expired")
    except BadSignature:
        raise HTTPException(status_code=400, detail="Invalid token")

    if Password.verify_totp(secret, request.code) != PasswordStatus.VALID:
        raise HTTPException(status_code=400, detail="Invalid OTP code")

    # 3. 将 secret 存储到用户的数据库记录中，启用 2FA
    user.two_factor = secret
    user = await user.save(session)