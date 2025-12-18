from typing import Literal

from sqlmodel import Field, UniqueConstraint

from .base import TableBase, SQLModelBase
from enum import StrEnum


# ==================== DTO 模型 ====================

class SiteConfigResponse(SQLModelBase):
    """站点配置响应 DTO"""

    title: str = "DiskNext"
    """网站标题"""

    themes: dict[str, str] = {}
    """网站主题配置"""

    default_theme: dict[str, str] = {}
    """默认主题RGB色号"""

    site_notice: str | None = None
    """网站公告"""

    user: dict[str, str | int | bool] = {}
    """用户信息"""

    logo_light: str | None = None
    """网站Logo URL"""

    logo_dark: str | None = None
    """网站Logo URL（深色模式）"""

    captcha_type: Literal["none", "default", "gcaptcha", "cloudflare turnstile"] = "none"
    """验证码类型"""

    captcha_key: str | None = None
    """验证码密钥"""


# ==================== 数据库模型 ====================

class SettingsType(StrEnum):
    """设置类型枚举"""

    ARIA2 = "aria2"
    AUTH = "auth"
    AUTHN = "authn"
    AVATAR = "avatar"
    BASIC = "basic"
    CAPTCHA = "captcha"
    CRON = "cron"
    FILE_EDIT = "file_edit"
    LOGIN = "login"
    MAIL = "mail"
    MAIL_TEMPLATE = "mail_template"
    MOBILE = "mobile"
    PATH = "path"
    PREVIEW = "preview"
    PWA = "pwa"
    REGISTER = "register"
    RETRY = "retry"
    SHARE = "share"
    SLAVE = "slave"
    TASK = "task"
    THUMB = "thumb"
    TIMEOUT = "timeout"
    UPLOAD = "upload"
    VERSION = "version"
    VIEW = "view"
    WOPI = "wopi"

# 数据库模型
class Setting(TableBase, table=True):
    """设置模型"""

    __table_args__ = (UniqueConstraint("type", "name", name="uq_setting_type_name"),)

    type: SettingsType = Field(max_length=255, description="设置类型/分组")
    name: str = Field(max_length=255, description="设置项名称")
    value: str | None = Field(default=None, description="设置值")