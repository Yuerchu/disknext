from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

import sqlmodels
from middleware.auth import auth_required
from middleware.dependencies import SessionDep
from sqlmodels import (
    BUILTIN_DEFAULT_COLORS, ThemePreset, UserThemeUpdateRequest,
    SettingOption, UserSettingUpdateRequest,
    ChangePasswordRequest,
    AuthnDetailResponse, AuthnRenameRequest,
    PolicySummary,
)
from sqlmodels.color import ThemeColorsBase
from sqlmodels.user import AvatarType
from sqlmodels.user_authn import UserAuthn
from utils import Password, http_exceptions
from utils.conf import appmeta
from utils.password.pwd import PasswordStatus, TwoFactorResponse, TwoFactorVerifyRequest
from .file_viewers import file_viewers_router

user_settings_router = APIRouter(
    prefix='/settings',
    tags=["user", "user_settings"],
    dependencies=[Depends(auth_required)],
)
user_settings_router.include_router(file_viewers_router)


@user_settings_router.get(
    path='/policies',
    summary='获取用户可选存储策略',
)
async def router_user_settings_policies(
        session: SessionDep,
        user: Annotated[sqlmodels.user.User, Depends(auth_required)],
) -> list[PolicySummary]:
    """
    获取当前用户所在组可选的存储策略列表

    返回用户组关联的所有存储策略的摘要信息。
    """
    group = await user.awaitable_attrs.group
    await session.refresh(group, ['policies'])
    return [
        PolicySummary(
            id=p.id, name=p.name, type=p.type,
            server=p.server, max_size=p.max_size, is_private=p.is_private,
        )
        for p in group.policies
    ]


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
        phone=user.phone,
        nickname=user.nickname,
        created_at=user.created_at,
        group_name=user.group.name,
        language=user.language,
        timezone=user.timezone,
        group_expires=user.group_expires,
        two_factor=user.two_factor_secret is not None,
        theme_preset_id=user.theme_preset_id,
        theme_colors=theme_colors,
    )


@user_settings_router.post(
    path='/avatar',
    summary='从文件上传头像',
    status_code=204,
)
async def router_user_settings_avatar(
        session: SessionDep,
        user: Annotated[sqlmodels.user.User, Depends(auth_required)],
        file: UploadFile = File(...),
) -> None:
    """
    上传头像文件

    认证：JWT token
    请求体：multipart/form-data，file 字段

    流程：
    1. 验证文件 MIME 类型（JPEG/PNG/GIF/WebP）
    2. 验证文件大小 <= avatar_size 设置（默认 2MB）
    3. 调用 Pillow 验证图片有效性并处理（居中裁剪、缩放 L/M/S）
    4. 保存三种尺寸的 WebP 文件
    5. 更新 User.avatar = "file"

    错误处理：
    - 400: 文件类型不支持 / 图片无法解析
    - 413: 文件过大
    """
    from utils.avatar import (
        ALLOWED_CONTENT_TYPES,
        get_avatar_settings,
        process_and_save_avatar,
    )

    # 验证 MIME 类型
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        http_exceptions.raise_bad_request(
            f"不支持的图片格式，允许: {', '.join(ALLOWED_CONTENT_TYPES)}"
        )

    # 读取并验证大小
    _, max_upload_size, _, _, _ = await get_avatar_settings(session)
    raw_bytes = await file.read()
    if len(raw_bytes) > max_upload_size:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大，最大允许 {max_upload_size} 字节",
        )

    # 处理并保存（内部会验证图片有效性，无效抛出 ValueError）
    try:
        await process_and_save_avatar(session, user.id, raw_bytes)
    except ValueError as e:
        http_exceptions.raise_bad_request(str(e))

    # 更新用户头像字段
    user.avatar = AvatarType.FILE
    user = await user.save(session)


@user_settings_router.put(
    path='/avatar',
    summary='设定为 Gravatar 头像',
    status_code=204,
)
async def router_user_settings_avatar_gravatar(
        session: SessionDep,
        user: Annotated[sqlmodels.user.User, Depends(auth_required)],
) -> None:
    """
    将头像切换为 Gravatar

    认证：JWT token

    流程：
    1. 验证用户有邮箱（Gravatar 基于邮箱 MD5）
    2. 如果当前是 FILE 头像，删除本地文件
    3. 更新 User.avatar = "gravatar"

    错误处理：
    - 400: 用户没有邮箱
    """
    from utils.avatar import delete_avatar_files

    if not user.email:
        http_exceptions.raise_bad_request("Gravatar 需要邮箱，请先绑定邮箱")

    if user.avatar == AvatarType.FILE:
        await delete_avatar_files(session, user.id)

    user.avatar = AvatarType.GRAVATAR
    user = await user.save(session)


@user_settings_router.delete(
    path='/avatar',
    summary='重置头像为默认',
    status_code=204,
)
async def router_user_settings_avatar_delete(
        session: SessionDep,
        user: Annotated[sqlmodels.user.User, Depends(auth_required)],
) -> None:
    """
    重置头像为默认

    认证：JWT token

    流程：
    1. 如果当前是 FILE 头像，删除本地文件
    2. 更新 User.avatar = "default"
    """
    from utils.avatar import delete_avatar_files

    if user.avatar == AvatarType.FILE:
        await delete_avatar_files(session, user.id)

    user.avatar = AvatarType.DEFAULT
    user = await user.save(session)


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

    user = await user.save(session)


@user_settings_router.patch(
    path='/password',
    summary='修改密码',
    status_code=status.HTTP_204_NO_CONTENT,
)
async def router_user_settings_change_password(
        session: SessionDep,
        user: Annotated[sqlmodels.user.User, Depends(auth_required)],
        request: ChangePasswordRequest,
) -> None:
    """
    修改当前用户密码

    请求体：
    - old_password: 当前密码
    - new_password: 新密码（至少 8 位）

    错误处理：
    - 400: 用户没有邮箱密码认证身份
    - 403: 当前密码错误
    """
    if not user.password_hash:
        http_exceptions.raise_bad_request("未设置密码")

    verify_result = Password.verify(user.password_hash, request.old_password)
    if verify_result == PasswordStatus.INVALID:
        http_exceptions.raise_forbidden("当前密码错误")

    user.password_hash = Password.hash(request.new_password)
    user = await user.save(session)


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
    user = await user.save(session)


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
    return await Password.generate_totp(name=user.email or str(user.id))


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

    将 2FA secret 存储到 email_password AuthIdentity 的 extra_data 中。
    """
    serializer = URLSafeTimedSerializer(appmeta.secret_key)

    try:
        secret = serializer.loads(request.setup_token, salt="2fa-setup-salt", max_age=600)
    except SignatureExpired:
        raise HTTPException(status_code=400, detail="Setup session expired")
    except BadSignature:
        raise HTTPException(status_code=400, detail="Invalid token")

    if Password.verify_totp(secret, request.code) != PasswordStatus.VALID:
        raise HTTPException(status_code=400, detail="Invalid OTP code")

    user.two_factor_secret = secret
    user = await user.save(session)


# ==================== WebAuthn 凭证管理 ====================

@user_settings_router.get(
    path='/authns',
    summary='列出用户所有 WebAuthn 凭证',
)
async def router_user_settings_authns(
    session: SessionDep,
    user: Annotated[sqlmodels.user.User, Depends(auth_required)],
) -> list[AuthnDetailResponse]:
    """
    列出当前用户所有已注册的 WebAuthn 凭证

    返回：
    - 凭证列表，包含 credential_id、name、device_type 等
    """
    authns: list[UserAuthn] = await UserAuthn.get(
        session,
        UserAuthn.user_id == user.id,
        fetch_mode="all",
    )
    return [AuthnDetailResponse.model_validate(authn, from_attributes=True) for authn in authns]


@user_settings_router.patch(
    path='/authn/{authn_id}',
    summary='重命名 WebAuthn 凭证',
)
async def router_user_settings_rename_authn(
    session: SessionDep,
    user: Annotated[sqlmodels.user.User, Depends(auth_required)],
    authn_id: int,
    request: AuthnRenameRequest,
) -> AuthnDetailResponse:
    """
    重命名一个 WebAuthn 凭证

    错误处理：
    - 404: 凭证不存在或不属于当前用户
    """
    authn: UserAuthn | None = await UserAuthn.get(
        session,
        (UserAuthn.id == authn_id) & (UserAuthn.user_id == user.id),
    )
    if not authn:
        http_exceptions.raise_not_found("WebAuthn 凭证不存在")

    authn.name = request.name
    authn = await authn.save(session)
    return AuthnDetailResponse.model_validate(authn, from_attributes=True)


@user_settings_router.delete(
    path='/authn/{authn_id}',
    summary='删除 WebAuthn 凭证',
    status_code=status.HTTP_204_NO_CONTENT,
)
async def router_user_settings_delete_authn(
    session: SessionDep,
    user: Annotated[sqlmodels.user.User, Depends(auth_required)],
    authn_id: int,
) -> None:
    """
    删除一个 WebAuthn 凭证

    同时删除对应的 AuthIdentity(provider=passkey) 记录。
    如果这是用户最后一个认证身份，拒绝删除。

    错误处理：
    - 404: 凭证不存在或不属于当前用户
    - 400: 不能删除最后一个认证身份
    """
    authn: UserAuthn | None = await UserAuthn.get(
        session,
        (UserAuthn.id == authn_id) & (UserAuthn.user_id == user.id),
    )
    if not authn:
        http_exceptions.raise_not_found("WebAuthn 凭证不存在")

    # PG 触发器 userauthn_last_auth_trg 会阻止删除最后一个认证方式
    await UserAuthn.delete(session, authn)
