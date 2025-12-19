from typing import Literal

from loguru import logger as log
from sqlmodel.ext.asyncio.session import AsyncSession

from models import LoginRequest, TokenResponse, User
from pkg.JWT.JWT import create_access_token, create_refresh_token
from .totp import verify_totp


async def Login(
    session: AsyncSession,
    login_request: LoginRequest,
) -> TokenResponse | bool | Literal["2fa_required", "2fa_invalid"] | None:
    """
    根据账号密码进行登录。

    如果登录成功，返回一个 TokenResponse 对象，包含访问令牌和刷新令牌以及它们的过期时间。
    如果登录异常，返回 `False`（未完成注册或账号被封禁）。
    如果登录失败，返回 `None`。
    如果需要两步验证但未提供验证码，返回 `"2fa_required"`。
    如果两步验证码无效，返回 `"2fa_invalid"`。

    :param session: 数据库会话
    :param login_request: 登录请求

    :return: TokenResponse 对象或状态码或 None
    """
    from pkg.password.pwd import Password

    # TODO: 验证码校验
    # captcha_setting = await Setting.get(
    #     session,
    #     and_(Setting.type == "auth", Setting.name == "login_captcha")
    # )
    # is_captcha_required = captcha_setting and captcha_setting.value == "1"

    # 获取用户信息
    current_user = await User.get(session, User.username == login_request.username, fetch_mode="one")

    # 验证用户是否存在
    if not current_user:
        log.debug(f"Cannot find user with username: {login_request.username}")
        return None

    # 验证密码是否正确
    if not Password.verify(current_user.password, login_request.password):
        log.debug(f"Password verification failed for user: {login_request.username}")
        return None

    # 验证用户是否可登录
    if not current_user.status:
        # 未完成注册 or 账号已被封禁
        return False

    # 检查两步验证
    if current_user.two_factor:
        # 用户已启用两步验证
        if not login_request.two_fa_code:
            log.debug(f"2FA required for user: {login_request.username}")
            return "2fa_required"

        # 验证 OTP 码
        if not verify_totp(current_user.two_factor, login_request.two_fa_code):
            log.debug(f"Invalid 2FA code for user: {login_request.username}")
            return "2fa_invalid"

    # 创建令牌
    access_token, access_expire = create_access_token(data={'sub': current_user.username})
    refresh_token, refresh_expire = create_refresh_token(data={'sub': current_user.username})

    return TokenResponse(
        access_token=access_token,
        access_expires=access_expire,
        refresh_token=refresh_token,
        refresh_expires=refresh_expire,
    )