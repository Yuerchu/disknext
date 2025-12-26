from uuid import uuid4

from loguru import logger

from middleware.dependencies import SessionDep
from models import LoginRequest, TokenResponse, User
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
    # TODO: 验证码校验
    # captcha_setting = await Setting.get(
    #     session,
    #     and_(Setting.type == "auth", Setting.name == "login_captcha")
    # )
    # is_captcha_required = captcha_setting and captcha_setting.value == "1"

    # 获取用户信息
    current_user = await User.get(session, User.username == login_request.username, fetch_mode="first")

    # 验证用户是否存在
    if not current_user:
        logger.debug(f"Cannot find user with username: {login_request.username}")
        http_exceptions.raise_unauthorized("Invalid username or password")

    # 验证密码是否正确
    if Password.verify(current_user.password, login_request.password) != PasswordStatus.VALID:
        logger.debug(f"Password verification failed for user: {login_request.username}")
        http_exceptions.raise_unauthorized("Invalid username or password")

    # 验证用户是否可登录
    if not current_user.status:
        http_exceptions.raise_forbidden("Your account is disabled")

    # 检查两步验证
    if current_user.two_factor:
        # 用户已启用两步验证
        if not login_request.two_fa_code:
            logger.debug(f"2FA required for user: {login_request.username}")
            http_exceptions.raise_precondition_required("2FA required")

        # 验证 OTP 码
        if Password.verify_totp(current_user.two_factor, login_request.two_fa_code) != PasswordStatus.VALID:
            logger.debug(f"Invalid 2FA code for user: {login_request.username}")
            http_exceptions.raise_unauthorized("Invalid 2FA code")

    # 创建令牌
    access_token = create_access_token(data={
        'sub': str(current_user.id), 
        'jti': str(uuid4())
    })
    refresh_token = create_refresh_token(data={
        'sub': str(current_user.id),
        'jti': str(uuid4())
    })

    return TokenResponse(
        access_token=access_token.access_token,
        access_expires=access_token.access_expires,
        refresh_token=refresh_token.refresh_token,
        refresh_expires=refresh_token.refresh_expires,
    )