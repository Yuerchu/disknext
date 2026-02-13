"""
WebAuthn RP（Relying Party）配置辅助模块

从数据库 Setting 中读取 siteURL / siteTitle，
解析出 rp_id、rp_name、origin，供注册/登录流程复用。
"""
from urllib.parse import urlparse

from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodels.setting import Setting, SettingsType


async def get_rp_config(session: AsyncSession) -> tuple[str, str, str]:
    """
    获取 WebAuthn RP 配置。

    :param session: 数据库会话
    :return: ``(rp_id, rp_name, origin)`` 元组

    - ``rp_id``: 站点域名（从 siteURL 解析，如 ``example.com``）
    - ``rp_name``: 站点标题
    - ``origin``: 完整 origin（如 ``https://example.com``）
    """
    site_url_setting: Setting | None = await Setting.get(
        session,
        (Setting.type == SettingsType.BASIC) & (Setting.name == "siteURL"),
    )
    site_title_setting: Setting | None = await Setting.get(
        session,
        (Setting.type == SettingsType.BASIC) & (Setting.name == "siteTitle"),
    )

    site_url: str = site_url_setting.value if site_url_setting and site_url_setting.value else "https://localhost"
    rp_name: str = site_title_setting.value if site_title_setting and site_title_setting.value else "DiskNext"

    parsed = urlparse(site_url)
    rp_id: str = parsed.hostname or "localhost"
    origin: str = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else site_url

    return rp_id, rp_name, origin
