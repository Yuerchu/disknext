from datetime import datetime
from enum import StrEnum
from typing import Literal, Optional, TYPE_CHECKING

from sqlmodel import Field, Relationship

from .base import TableBase, SQLModelBase

if TYPE_CHECKING:
    from .group import Group
    from .download import Download
    from .object import Object
    from .order import Order
    from .share import Share
    from .storage_pack import StoragePack
    from .tag import Tag
    from .task import Task
    from .user_authn import UserAuthn
    from .webdav import WebDAV

"""
Option 需求
- 主题 跟随系统/浅色/深色
- 颜色方案 参考 ThemeResponse
- 语言
- 时区
- 切换到不同存储策略是否提醒
"""

class AvatarType(StrEnum):
    """头像类型枚举"""
    
    DEFAULT = "default"
    GRAVATAR = "gravatar"
    FILE = "file"


# ==================== Base 模型 ====================

class UserBase(SQLModelBase):
    """用户基础字段，供数据库模型和 DTO 共享"""

    username: str
    """用户名"""

    status: bool = True
    """用户状态: True=正常, False=封禁"""

    score: int = 0
    """用户积分"""


# ==================== DTO 模型 ====================

class LoginRequest(SQLModelBase):
    """登录请求 DTO"""

    username: str
    """用户名或邮箱"""

    password: str
    """用户密码"""

    captcha: str | None = None
    """验证码"""

    two_fa_code: str | None = None
    """两步验证代码"""


class WebAuthnInfo(SQLModelBase):
    """WebAuthn 信息 DTO"""

    credential_id: str
    """凭证 ID"""

    credential_public_key: str
    """凭证公钥"""

    sign_count: int
    """签名计数器"""

    credential_device_type: bool
    """是否为平台认证器"""

    credential_backed_up: bool
    """凭证是否已备份"""

    transports: list[str]
    """支持的传输方式"""


class ThemeResponse(SQLModelBase):
    """主题响应 DTO"""

    primary: str = "#3f51b5"
    """主色调"""

    secondary: str = "#f50057"
    """次要色"""

    accent: str = "#9c27b0"
    """强调色"""

    dark: str = "#1d1d1d"
    """深色"""

    dark_page: str = "#121212"
    """深色页面背景"""

    positive: str = "#21ba45"
    """正面/成功色"""

    negative: str = "#c10015"
    """负面/错误色"""

    info: str = "#31ccec"
    """信息色"""

    warning: str = "#f2c037"
    """警告色"""


class TokenResponse(SQLModelBase):
    """访问令牌响应 DTO"""

    access_expires: datetime
    """访问令牌过期时间"""

    access_token: str
    """访问令牌"""

    refresh_expires: datetime
    """刷新令牌过期时间"""

    refresh_token: str
    """刷新令牌"""


class UserResponse(UserBase):
    """用户响应 DTO"""

    id: int
    """用户ID"""

    nickname: str | None = None
    """用户昵称"""

    avatar: Literal["default", "gravatar", "file"] = "default"
    """头像类型"""

    created_at: datetime
    """用户创建时间"""

    preferred_theme: ThemeResponse | None = None
    """用户首选主题"""

    anonymous: bool = False
    """是否为匿名用户"""

    group: "GroupResponse | None" = None
    """用户所属用户组"""

    tags: list[str] = []
    """用户标签列表"""


class UserPublic(UserBase):
    """用户公开信息 DTO，用于 API 响应"""

    id: int | None = None
    """用户ID"""

    nick: str | None = None
    """昵称"""

    storage: int = 0
    """已用存储空间（字节）"""

    avatar: str | None = None
    """头像地址"""

    group_expires: datetime | None = None
    """用户组过期时间"""

    group_id: int | None = None
    """所属用户组ID"""

    created_at: datetime | None = None
    """创建时间"""

    updated_at: datetime | None = None
    """更新时间"""


class UserSettingResponse(SQLModelBase):
    """用户设置响应 DTO"""

    authn: "AuthnResponse | None" = None
    """认证信息"""

    group_expires: datetime | None = None
    """用户组过期时间"""

    prefer_theme: str = "#5898d4"
    """用户首选主题"""

    qq: str | None = None
    """QQ号"""

    themes: dict[str, str] = {}
    """用户主题配置"""

    two_factor: bool = False
    """是否启用两步验证"""

    uid: int = 0
    """用户UID"""


# 前向引用导入
from .group import GroupResponse  # noqa: E402
from .user_authn import AuthnResponse  # noqa: E402

# 更新前向引用
UserResponse.model_rebuild()
UserSettingResponse.model_rebuild()


# ==================== 数据库模型 ====================

class User(UserBase, TableBase, table=True):
    """用户模型"""

    username: str = Field(max_length=50, unique=True, index=True)
    """用户名，唯一，一经注册不可更改"""

    nickname: str | None = Field(default=None, max_length=50)
    """用于公开展示的名字，可使用真实姓名或昵称"""

    password: str = Field(max_length=255)
    """用户密码（加密后）"""

    status: bool = Field(default=True, sa_column_kwargs={"server_default": "true"})
    """用户状态: True=正常, False=封禁"""

    storage: int = Field(default=0, sa_column_kwargs={"server_default": "0"}, ge=0)
    """已用存储空间（字节）"""

    two_factor: str | None = Field(default=None, min_length=32, max_length=32)
    """两步验证密钥"""

    avatar: str = Field(default="default", max_length=255)
    """头像地址"""

    options: str | None = None
    """[TODO] 用户个人设置 需要更改，参考上方的需求"""

    github_open_id: str | None = Field(default=None, unique=True, index=True)
    """Github OpenID"""

    qq_open_id: str | None = Field(default=None, unique=True, index=True)
    """QQ OpenID"""

    score: int = Field(default=0, sa_column_kwargs={"server_default": "0"}, ge=0)
    """用户积分"""

    group_expires: datetime | None = None
    """当前用户组过期时间"""

    phone: str | None = Field(default=None, max_length=32, unique=True, index=True)
    """手机号"""

    # 外键
    group_id: int = Field(foreign_key="group.id", index=True)
    """所属用户组ID"""

    previous_group_id: int | None = Field(default=None, foreign_key="group.id")
    """之前的用户组ID（用于过期后恢复）"""

    # [TODO] 待考虑：根目录 Object ID

    # 关系
    group: "Group" = Relationship(
        back_populates="user",
        sa_relationship_kwargs={
            "foreign_keys": "User.group_id"
        }
    )
    previous_group: Optional["Group"] = Relationship(
        back_populates="previous_user",
        sa_relationship_kwargs={
            "foreign_keys": "User.previous_group_id"
        }
    )

    downloads: list["Download"] = Relationship(back_populates="user")
    objects: list["Object"] = Relationship(back_populates="owner")
    """用户的所有对象（文件和目录）"""
    orders: list["Order"] = Relationship(back_populates="user")
    shares: list["Share"] = Relationship(back_populates="user")
    storage_packs: list["StoragePack"] = Relationship(back_populates="user")
    tags: list["Tag"] = Relationship(back_populates="user")
    tasks: list["Task"] = Relationship(back_populates="user")
    webdavs: list["WebDAV"] = Relationship(back_populates="user")
    authns: list["UserAuthn"] = Relationship(back_populates="user")

    def to_public(self) -> "UserPublic":
        """转换为公开 DTO，排除敏感字段"""
        return UserPublic.model_validate(self)