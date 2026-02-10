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

    site_notice: str | None = None
    """网站公告"""

    user: UserResponse | None = None
    """用户信息"""

    logo_light: str | None = None
    """网站Logo URL"""

    logo_dark: str | None = None
    """网站Logo URL（深色模式）"""

    register_enabled: bool = True
    """是否允许注册"""

    login_captcha: bool = False
    """登录是否需要验证码"""

    reg_captcha: bool = False
    """注册是否需要验证码"""

    forget_captcha: bool = False
    """找回密码是否需要验证码"""

    captcha_type: CaptchaType = CaptchaType.DEFAULT
    """验证码类型"""

    captcha_key: str | None = None
    """验证码 public key（DEFAULT 类型时为 None）"""


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
    OAUTH = "oauth"
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
class Setting(SettingItem, TableBaseMixin):
    """设置模型，继承 SettingItem 中的 name 和 value 字段"""

    __table_args__ = (UniqueConstraint("type", "name", name="uq_setting_type_name"),)

    type: SettingsType
    """设置类型/分组（覆盖基类的 str 类型为枚举类型）"""