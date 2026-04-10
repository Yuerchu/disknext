"""
WebAuthn RP（Relying Party）配置辅助模块

从 ServerConfig 中读取 site_url / site_title，
解析出 rp_id、rp_name、origin，供注册/登录流程复用。
"""
from urllib.parse import urlparse

from sqlmodels.server_config import ServerConfig


def get_rp_config(config: ServerConfig) -> tuple[str, str, str]:
    """
    获取 WebAuthn RP 配置。

    :param config: 服务器配置
    :return: ``(rp_id, rp_name, origin)`` 元组

    - ``rp_id``: 站点域名（从 site_url 解析，如 ``example.com``）
    - ``rp_name``: 站点标题
    - ``origin``: 完整 origin（如 ``https://example.com``）
    """
    site_url: str = config.site_url
    rp_name: str = config.site_title

    parsed = urlparse(site_url)
    rp_id: str = parsed.hostname or "localhost"
    origin: str = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else site_url

    return rp_id, rp_name, origin
