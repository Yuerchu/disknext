from fastapi import APIRouter

from middleware.dependencies import SessionDep
from sqlmodels import ResponseBase, Setting, SettingsType, SiteConfigResponse
from sqlmodels.setting import CaptchaType
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
    path='/config',
    summary='站点全局配置',
    description='获取站点全局配置，包括验证码设置、注册开关等。',
)
async def router_site_config(session: SessionDep) -> SiteConfigResponse:
    """
    获取站点全局配置

    无需认证。前端在初始化时调用此端点获取验证码类型、
    登录/注册/找回密码是否需要验证码等配置。
    """
    # 批量查询所需设置
    settings: list[Setting] = await Setting.get(
        session,
        (Setting.type == SettingsType.BASIC) |
        (Setting.type == SettingsType.LOGIN) |
        (Setting.type == SettingsType.REGISTER) |
        (Setting.type == SettingsType.CAPTCHA),
        fetch_mode="all",
    )

    # 构建 name→value 映射
    s: dict[str, str | None] = {item.name: item.value for item in settings}

    # 根据 captcha_type 选择对应的 public key
    captcha_type_str = s.get("captcha_type", "default")
    captcha_type = CaptchaType(captcha_type_str) if captcha_type_str else CaptchaType.DEFAULT
    captcha_key: str | None = None
    if captcha_type == CaptchaType.GCAPTCHA:
        captcha_key = s.get("captcha_ReCaptchaKey") or None
    elif captcha_type == CaptchaType.CLOUD_FLARE_TURNSTILE:
        captcha_key = s.get("captcha_CloudflareKey") or None

    return SiteConfigResponse(
        title=s.get("siteName") or "DiskNext",
        register_enabled=s.get("register_enabled") == "1",
        login_captcha=s.get("login_captcha") == "1",
        reg_captcha=s.get("reg_captcha") == "1",
        forget_captcha=s.get("forget_captcha") == "1",
        captcha_type=captcha_type,
        captcha_key=captcha_key,
    )