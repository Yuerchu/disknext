from fastapi import APIRouter

from middleware.dependencies import SessionDep, ServerConfigDep
from sqlmodels import (
    ResponseBase, SiteConfigResponse,
    ThemePreset, ThemePresetResponse, ThemePresetListResponse,
    AuthMethodConfig,
)
from sqlmodels.auth_identity import AuthProviderType
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
        themes=[ThemePresetResponse.model_validate(p, from_attributes=True) for p in presets]
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
    response = SiteConfigResponse.model_validate(config, from_attributes=True)
    response.auth_methods = [
        AuthMethodConfig(provider=AuthProviderType.EMAIL_PASSWORD, is_enabled=config.is_auth_email_password_enabled),
        AuthMethodConfig(provider=AuthProviderType.PHONE_SMS, is_enabled=config.is_auth_phone_sms_enabled),
        AuthMethodConfig(provider=AuthProviderType.GITHUB, is_enabled=config.is_github_enabled),
        AuthMethodConfig(provider=AuthProviderType.QQ, is_enabled=config.is_qq_enabled),
        AuthMethodConfig(provider=AuthProviderType.PASSKEY, is_enabled=config.is_auth_passkey_enabled),
    ]
    return response