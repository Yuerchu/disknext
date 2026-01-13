from fastapi import APIRouter

from middleware.dependencies import SessionDep
from models import ResponseBase, Setting, SettingsType, SiteConfigResponse
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
    description='Get the configuration file.',
    response_model=ResponseBase,
)
async def router_site_config(session: SessionDep) -> SiteConfigResponse:
    """
    Get the configuration file.

    Returns:
        dict: The site configuration.
    """
    return SiteConfigResponse(
        title=await Setting.get(session, (Setting.type == SettingsType.BASIC) & (Setting.name == "siteName")),
    )