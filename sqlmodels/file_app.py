"""
文件查看器应用模块

提供文件预览应用选择器系统的数据模型和 DTO。
类似 Android 的"使用什么应用打开"机制：
- 管理员注册应用（内置/iframe/WOPI）
- 用户按扩展名查询可用查看器
- 用户可设置"始终使用"偏好
- 支持用户组级别的访问控制

架构：
    FileApp (应用注册表)
    ├── FileAppExtension (扩展名关联)
    ├── FileAppGroupLink (用户组访问控制)
    └── UserFileAppDefault (用户默认偏好)
"""
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlmodel import Field, Relationship, UniqueConstraint

from sqlmodel_ext import SQLModelBase, TableBaseMixin, UUIDTableBaseMixin

if TYPE_CHECKING:
    from .group import Group


# ==================== 枚举 ====================

class FileAppType(StrEnum):
    """文件应用类型"""

    BUILTIN = "builtin"
    """前端内置查看器（如 pdf.js, Monaco）"""

    IFRAME = "iframe"
    """iframe 内嵌第三方服务"""

    WOPI = "wopi"
    """WOPI 协议（OnlyOffice / Collabora）"""


# ==================== Link 表 ====================

class FileAppGroupLink(SQLModelBase, table=True):
    """应用-用户组访问控制关联表"""

    app_id: UUID = Field(foreign_key="fileapp.id", primary_key=True, ondelete="CASCADE")
    """关联的应用UUID"""

    group_id: UUID = Field(foreign_key="group.id", primary_key=True, ondelete="CASCADE")
    """关联的用户组UUID"""


# ==================== DTO 模型 ====================

class FileAppSummary(SQLModelBase):
    """查看器列表项 DTO，用于选择器弹窗"""

    id: UUID
    """应用UUID"""

    name: str
    """应用名称"""

    app_key: str
    """应用唯一标识"""

    type: FileAppType
    """应用类型"""

    icon: str | None = None
    """图标名称/URL"""

    description: str | None = None
    """应用描述"""

    iframe_url_template: str | None = None
    """iframe URL 模板"""

    wopi_editor_url_template: str | None = None
    """WOPI 编辑器 URL 模板"""


class FileViewersResponse(SQLModelBase):
    """查看器查询响应 DTO"""

    viewers: list[FileAppSummary] = []
    """可用查看器列表（已按 priority 排序）"""

    default_viewer_id: UUID | None = None
    """用户默认查看器UUID（如果已设置"始终使用"）"""


class SetDefaultViewerRequest(SQLModelBase):
    """设置默认查看器请求 DTO"""

    extension: str = Field(max_length=20)
    """文件扩展名（小写，无点号）"""

    app_id: UUID
    """应用UUID"""


class UserFileAppDefaultResponse(SQLModelBase):
    """用户默认查看器响应 DTO"""

    id: UUID
    """记录UUID"""

    extension: str
    """扩展名"""

    app: FileAppSummary
    """关联的应用摘要"""


class FileAppCreateRequest(SQLModelBase):
    """管理员创建应用请求 DTO"""

    name: str = Field(max_length=100)
    """应用名称"""

    app_key: str = Field(max_length=50)
    """应用唯一标识"""

    type: FileAppType
    """应用类型"""

    icon: str | None = Field(default=None, max_length=255)
    """图标名称/URL"""

    description: str | None = Field(default=None, max_length=500)
    """应用描述"""

    is_enabled: bool = True
    """是否启用"""

    is_restricted: bool = False
    """是否限制用户组访问"""

    iframe_url_template: str | None = Field(default=None, max_length=1024)
    """iframe URL 模板"""

    wopi_discovery_url: str | None = Field(default=None, max_length=512)
    """WOPI 发现端点 URL"""

    wopi_editor_url_template: str | None = Field(default=None, max_length=1024)
    """WOPI 编辑器 URL 模板"""

    extensions: list[str] = []
    """关联的扩展名列表"""

    allowed_group_ids: list[UUID] = []
    """允许访问的用户组UUID列表"""


class FileAppUpdateRequest(SQLModelBase):
    """管理员更新应用请求 DTO（所有字段可选）"""

    name: str | None = Field(default=None, max_length=100)
    """应用名称"""

    app_key: str | None = Field(default=None, max_length=50)
    """应用唯一标识"""

    type: FileAppType | None = None
    """应用类型"""

    icon: str | None = Field(default=None, max_length=255)
    """图标名称/URL"""

    description: str | None = Field(default=None, max_length=500)
    """应用描述"""

    is_enabled: bool | None = None
    """是否启用"""

    is_restricted: bool | None = None
    """是否限制用户组访问"""

    iframe_url_template: str | None = Field(default=None, max_length=1024)
    """iframe URL 模板"""

    wopi_discovery_url: str | None = Field(default=None, max_length=512)
    """WOPI 发现端点 URL"""

    wopi_editor_url_template: str | None = Field(default=None, max_length=1024)
    """WOPI 编辑器 URL 模板"""


class FileAppResponse(SQLModelBase):
    """管理员应用详情响应 DTO"""

    id: UUID
    """应用UUID"""

    name: str
    """应用名称"""

    app_key: str
    """应用唯一标识"""

    type: FileAppType
    """应用类型"""

    icon: str | None = None
    """图标名称/URL"""

    description: str | None = None
    """应用描述"""

    is_enabled: bool = True
    """是否启用"""

    is_restricted: bool = False
    """是否限制用户组访问"""

    iframe_url_template: str | None = None
    """iframe URL 模板"""

    wopi_discovery_url: str | None = None
    """WOPI 发现端点 URL"""

    wopi_editor_url_template: str | None = None
    """WOPI 编辑器 URL 模板"""

    extensions: list[str] = []
    """关联的扩展名列表"""

    allowed_group_ids: list[UUID] = []
    """允许访问的用户组UUID列表"""

    @classmethod
    def from_app(
        cls,
        app: "FileApp",
        extensions: list["FileAppExtension"],
        group_links: list[FileAppGroupLink],
    ) -> "FileAppResponse":
        """从 ORM 对象构建 DTO"""
        return cls(
            id=app.id,
            name=app.name,
            app_key=app.app_key,
            type=app.type,
            icon=app.icon,
            description=app.description,
            is_enabled=app.is_enabled,
            is_restricted=app.is_restricted,
            iframe_url_template=app.iframe_url_template,
            wopi_discovery_url=app.wopi_discovery_url,
            wopi_editor_url_template=app.wopi_editor_url_template,
            extensions=[ext.extension for ext in extensions],
            allowed_group_ids=[link.group_id for link in group_links],
        )


class FileAppListResponse(SQLModelBase):
    """管理员应用列表响应 DTO"""

    apps: list[FileAppResponse] = []
    """应用列表"""

    total: int = 0
    """总数"""


class ExtensionUpdateRequest(SQLModelBase):
    """扩展名全量替换请求 DTO"""

    extensions: list[str]
    """扩展名列表（小写，无点号）"""


class GroupAccessUpdateRequest(SQLModelBase):
    """用户组权限全量替换请求 DTO"""

    group_ids: list[UUID]
    """允许访问的用户组UUID列表"""


class WopiSessionResponse(SQLModelBase):
    """WOPI 会话响应 DTO"""

    wopi_src: str
    """WOPI 源 URL"""

    access_token: str
    """WOPI 访问令牌"""

    access_token_ttl: int
    """令牌过期时间戳（毫秒，WOPI 规范要求）"""

    editor_url: str
    """完整的编辑器 URL"""


class WopiDiscoveredExtension(SQLModelBase):
    """单个 WOPI Discovery 发现的扩展名"""

    extension: str
    """文件扩展名"""

    action_url: str
    """处理后的动作 URL 模板"""


class WopiDiscoveryResponse(SQLModelBase):
    """WOPI Discovery 结果响应 DTO"""

    discovered_extensions: list[WopiDiscoveredExtension] = []
    """发现的扩展名及其 URL 模板"""

    app_names: list[str] = []
    """WOPI 服务端报告的应用名称（如 Writer、Calc、Impress）"""

    applied_count: int = 0
    """已应用到 FileAppExtension 的数量"""


# ==================== 数据库模型 ====================

class FileApp(SQLModelBase, UUIDTableBaseMixin):
    """文件查看器应用注册表"""

    name: str = Field(max_length=100)
    """应用名称"""

    app_key: str = Field(max_length=50, unique=True, index=True)
    """应用唯一标识，前端路由用"""

    type: FileAppType
    """应用类型"""

    icon: str | None = Field(default=None, max_length=255)
    """图标名称/URL"""

    description: str | None = Field(default=None, max_length=500)
    """应用描述"""

    is_enabled: bool = True
    """是否启用"""

    is_restricted: bool = False
    """是否限制用户组访问"""

    iframe_url_template: str | None = Field(default=None, max_length=1024)
    """iframe URL 模板，支持 {file_url} 占位符"""

    wopi_discovery_url: str | None = Field(default=None, max_length=512)
    """WOPI 客户端发现端点 URL"""

    wopi_editor_url_template: str | None = Field(default=None, max_length=1024)
    """WOPI 编辑器 URL 模板，支持 {wopi_src} {access_token} {access_token_ttl}"""

    # 关系
    extensions: list["FileAppExtension"] = Relationship(
        back_populates="app",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )

    user_defaults: list["UserFileAppDefault"] = Relationship(
        back_populates="app",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )

    allowed_groups: list["Group"] = Relationship(
        link_model=FileAppGroupLink,
    )

    def to_summary(self) -> FileAppSummary:
        """转换为摘要 DTO"""
        return FileAppSummary(
            id=self.id,
            name=self.name,
            app_key=self.app_key,
            type=self.type,
            icon=self.icon,
            description=self.description,
            iframe_url_template=self.iframe_url_template,
            wopi_editor_url_template=self.wopi_editor_url_template,
        )


class FileAppExtension(SQLModelBase, TableBaseMixin):
    """扩展名关联表"""

    __table_args__ = (
        UniqueConstraint("app_id", "extension", name="uq_fileappextension_app_extension"),
    )

    app_id: UUID = Field(foreign_key="fileapp.id", index=True, ondelete="CASCADE")
    """关联的应用UUID"""

    extension: str = Field(max_length=20, index=True)
    """扩展名（小写，无点号）"""

    priority: int = Field(default=0, ge=0)
    """排序优先级（越小越优先）"""

    wopi_action_url: str | None = Field(default=None, max_length=2048)
    """WOPI 动作 URL 模板（Discovery 自动填充），支持 {wopi_src} {access_token} {access_token_ttl}"""

    # 关系
    app: FileApp = Relationship(back_populates="extensions")


class UserFileAppDefault(SQLModelBase, UUIDTableBaseMixin):
    """用户"始终使用"偏好"""

    __table_args__ = (
        UniqueConstraint("user_id", "extension", name="uq_userfileappdefault_user_extension"),
    )

    user_id: UUID = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    """用户UUID"""

    extension: str = Field(max_length=20)
    """扩展名（小写，无点号）"""

    app_id: UUID = Field(foreign_key="fileapp.id", index=True, ondelete="CASCADE")
    """关联的应用UUID"""

    # 关系
    app: FileApp = Relationship(back_populates="user_defaults")

    def to_response(self) -> UserFileAppDefaultResponse:
        """转换为响应 DTO（需预加载 app 关系）"""
        return UserFileAppDefaultResponse(
            id=self.id,
            extension=self.extension,
            app=self.app.to_summary(),
        )
