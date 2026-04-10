from fastapi import APIRouter

from middleware.dependencies import SessionDep, ServerConfigDep
from sqlmodels import (
    ResponseBase, SiteConfigResponse,
    ThemePreset, ThemePresetResponse, ThemePresetListResponse,
    AuthMethodConfig,
)
from sqlmodels.auth_identity import AuthProviderType
from sqlmodels.server_config import CaptchaType
from utils import http_exceptions

site_router = APIRouter(
    prefix="/site",
    tags=["site"],
)

@site_router.get(
    path="/ping",
    summary="测试用路由",
    description="A simple endpoint to check if the site is up and running.",
    response_model=ResponseBase,
)
def router_site_ping() -> ResponseBase:
    """
    Ping the site to check if it is up and running.

    Returns:
        str: A message indicating the site is running.
    """
    return ResponseBase()


@site_router.get(
    path='/captcha',
    summary='验证码',
    description='Get a Base64 captcha image.',
    response_model=ResponseBase,
)
def router_site_captcha():
    """
    Get a Base64 captcha image.

    Returns:
        str: A Base64 encoded string of the captcha image.
    """
    http_exceptions.raise_not_implemented()

@site_router.get(
    path='/themes',
    summary='获取主题预设列表',
)
async def router_site_themes(session: SessionDep) -> ThemePresetListResponse:
    """
    获取所有主题预设列表

    无需认证，前端初始化时调用。
    """
    presets: list[ThemePreset] = await ThemePreset.get(session, fetch_mode="all")
    return ThemePresetListResponse(
        themes=[ThemePresetResponse.from_preset(p) for p in presets]
    )


@site_router.get(
    path='/config',
    summary='站点全局配置',
    description='获取站点全局配置，包括验证码设置、注册开关等。',
)
async def router_site_config(config: ServerConfigDep) -> SiteConfigResponse:
    """
    获取站点全局配置

    无需认证。前端在初始化时调用此端点获取验证码类型、
    登录/注册/找回密码是否需要验证码、可用的认证方式等配置。
    """
    # 根据 captcha_type 选择对应的 public key
    captcha_key: str | None = None
    if config.captcha_type == CaptchaType.GCAPTCHA:
        captcha_key = config.captcha_recaptcha_key or None
    elif config.captcha_type == CaptchaType.CLOUD_FLARE_TURNSTILE:
        captcha_key = config.captcha_cloudflare_key or None

    # 构建认证方式列表
    auth_methods: list[AuthMethodConfig] = [
        AuthMethodConfig(provider=AuthProviderType.EMAIL_PASSWORD, is_enabled=config.is_auth_email_password_enabled),
        AuthMethodConfig(provider=AuthProviderType.PHONE_SMS, is_enabled=config.is_auth_phone_sms_enabled),
        AuthMethodConfig(provider=AuthProviderType.GITHUB, is_enabled=config.is_github_enabled),
        AuthMethodConfig(provider=AuthProviderType.QQ, is_enabled=config.is_qq_enabled),
        AuthMethodConfig(provider=AuthProviderType.PASSKEY, is_enabled=config.is_auth_passkey_enabled),
        AuthMethodConfig(provider=AuthProviderType.MAGIC_LINK, is_enabled=config.is_auth_magic_link_enabled),
    ]

    return SiteConfigResponse(
        title=config.site_name,
        logo_light=config.logo_light or None,
        logo_dark=config.logo_dark or None,
        register_enabled=config.is_register_enabled,
        login_captcha=config.is_login_captcha,
        reg_captcha=config.is_reg_captcha,
        forget_captcha=config.is_forget_captcha,
        captcha_type=config.captcha_type,
        captcha_key=captcha_key,
        auth_methods=auth_methods,
        password_required=config.is_auth_password_required,
        phone_binding_required=config.is_auth_phone_binding_required,
        email_binding_required=config.is_auth_email_binding_required,
        avatar_max_size=config.avatar_size,
        footer_code=config.footer_code or None,
        tos_url=config.tos_url or None,
        privacy_url=config.privacy_url or None,
    )