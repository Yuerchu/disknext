from uuid import uuid4

from loguru import logger

from middleware.dependencies import SessionDep
from sqlmodels import LoginRequest, TokenResponse, User
from sqlmodels.group import GroupClaims, GroupOptions
from sqlmodels.user import UserStatus
from utils import http_exceptions
from utils.JWT import create_access_token, create_refresh_token
from utils.password.pwd import Password, PasswordStatus


async def login(
    session: SessionDep,
    login_request: LoginRequest,
) -> TokenResponse:
    """
    根据账号密码进行登录。
    如果登录成功，返回一个 TokenResponse 对象，包含访问令牌和刷新令牌以及它们的过期时间。

    :param session: 数据库会话
    :param login_request: 登录请求

    :return: TokenResponse 对象或状态码或 None
    """
    # 获取用户信息（预加载 group 关系）
    current_user: User = await User.get(
        session,
        User.email == login_request.email,
        fetch_mode="first",
        load=User.group,
    )   #type: ignore

    # 验证用户是否存在
    if not current_user:
        logger.debug(f"Cannot find user with email: {login_request.email}")
        http_exceptions.raise_unauthorized("Invalid email or password")

    # 验证密码是否正确
    if Password.verify(current_user.password, login_request.password) != PasswordStatus.VALID:
        logger.debug(f"Password verification failed for user: {login_request.email}")
        http_exceptions.raise_unauthorized("Invalid email or password")

    # 验证用户是否可登录（修复：显式枚举比较，StrEnum 永远 truthy）
    if current_user.status != UserStatus.ACTIVE:
        http_exceptions.raise_forbidden("Your account is disabled")

    # 检查两步验证
    if current_user.two_factor:
        # 用户已启用两步验证
        if not login_request.two_fa_code:
            logger.debug(f"2FA required for user: {login_request.email}")
            http_exceptions.raise_precondition_required("2FA required")

        # 验证 OTP 码
        if Password.verify_totp(current_user.two_factor, login_request.two_fa_code) != PasswordStatus.VALID:
            logger.debug(f"Invalid 2FA code for user: {login_request.email}")
            http_exceptions.raise_unauthorized("Invalid 2FA code")

    # 加载 GroupOptions
    group_options: GroupOptions | None = await GroupOptions.get(
        session,
        GroupOptions.group_id == current_user.group_id,
    )

    # 构建权限快照
    current_user.group.options = group_options
    group_claims = GroupClaims.from_group(current_user.group)

    # 创建令牌
    access_token = create_access_token(
        sub=current_user.id,
        jti=uuid4(),
        status=current_user.status.value,
        group=group_claims,
    )
    refresh_token = create_refresh_token(
        sub=current_user.id,
        jti=uuid4()
    )

    return TokenResponse(
        access_token=access_token.access_token,
        access_expires=access_token.access_expires,
        refresh_token=refresh_token.refresh_token,
        refresh_expires=refresh_token.refresh_expires,
    )
