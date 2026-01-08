from enum import StrEnum

from sqlmodel import UniqueConstraint

from .base import SQLModelBase
from .mixin import TableBaseMixin
from .user import UserResponse

class CaptchaType(StrEnum):
    """验证码类型枚举"""
    DEFAULT = "default"
    GCAPTCHA = "gcaptcha"
    CLOUD_FLARE_TURNSTILE = "cloudflare turnstile"

# ==================== DTO 模型 ====================

class SiteConfigResponse(SQLModelBase):
    """站点配置响应 DTO"""

    title: str = "DiskNext"
    """网站标题"""

    # themes: dict[str, str] = {}
    # """网站主题配置"""

    # default_theme: dict[str, str] = {}
    # """默认主题RGB色号"""

    site_notice: str | None = None
    """网站公告"""

    user: UserResponse
    """用户信息"""

    logo_light: str | None = None
    """网站Logo URL"""

    logo_dark: str | None = None
    """网站Logo URL（深色模式）"""

    captcha_type: CaptchaType | None = None
    """验证码类型"""

    captcha_key: str | None = None
    """验证码密钥"""


# ==================== 管理员设置 DTO ====================

class SettingItem(SQLModelBase):
    """单个设置项 DTO"""

    type: str
    """设置类型"""

    name: str
    """设置项名称"""

    value: str | None = None
    """设置值"""


class SettingsListResponse(SQLModelBase):
    """获取设置列表响应 DTO"""

    settings: list[SettingItem]
    """设置项列表"""

    total: int
    """总数"""


class SettingsUpdateRequest(SQLModelBase):
    """更新设置请求 DTO"""

    settings: list[SettingItem]
    """要更新的设置项列表"""


class SettingsUpdateResponse(SQLModelBase):
    """更新设置响应 DTO"""

    updated: int
    """更新的设置项数量"""

    created: int
    """新建的设置项数量"""


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
class Setting(SQLModelBase, TableBaseMixin):
    """设置模型"""

    __table_args__ = (UniqueConstraint("type", "name", name="uq_setting_type_name"),)

    type: SettingsType
    """设置类型/分组"""

    name: str
    """设置项名称"""

    value: str | None
    """设置值"""