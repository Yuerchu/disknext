"""
Scope 权限系统

格式: resource:action:visibility  或  resource:*（通配符）

匹配规则:
- ``files:*`` 匹配 files 下所有 action + visibility
- ``files:read:all`` 包含 ``files:read:own``（all ⊃ own）
- 不同 resource 互不匹配
"""
from enum import StrEnum

from sqlmodel_ext import SQLModelBase


class ScopeResource(StrEnum):
    """权限资源类型"""

    FILES = "files"
    """文件/文件夹管理"""

    SHARES = "shares"
    """分享管理"""

    WEBDAV = "webdav"
    """WebDAV 访问"""

    ARIA2 = "aria2"
    """离线下载"""

    ADMIN_USERS = "admin.users"
    """管理用户"""

    ADMIN_GROUPS = "admin.groups"
    """管理用户组"""

    ADMIN_NODES = "admin.nodes"
    """管理节点"""

    ADMIN_SETTINGS = "admin.settings"
    """管理站点设置"""

    ADMIN_POLICIES = "admin.policies"
    """管理存储策略"""

    ADMIN_FILES = "admin.files"
    """管理全站文件"""

    ADMIN_SHARES = "admin.shares"
    """管理全站分享"""

    ADMIN_TASKS = "admin.tasks"
    """管理任务"""

    ADMIN_FILE_APPS = "admin.file_apps"
    """管理文件应用"""

    ADMIN_THEMES = "admin.themes"
    """管理主题预设"""

    ADMIN_DASHBOARD = "admin.dashboard"
    """管理后台概览/统计"""


class ScopeAction(StrEnum):
    """权限操作类型"""

    CREATE = "create"
    """创建"""

    READ = "read"
    """读取"""

    WRITE = "write"
    """修改（重命名、移动、属性）"""

    DELETE = "delete"
    """删除"""

    DOWNLOAD = "download"
    """下载/获取源地址"""

    WILDCARD = "*"
    """通配符（管理员）"""


class ScopeVisibility(StrEnum):
    """权限可见范围"""

    OWN = "own"
    """自己的资源"""

    ALL = "all"
    """所有资源（管理员）"""


class Scope(SQLModelBase):
    """
    解析后的单个 scope 值。

    支持两种格式：
    - 完整: ``files:read:own``
    - 通配符: ``files:*``
    """

    resource: ScopeResource
    """资源类型"""

    action: ScopeAction
    """操作类型"""

    visibility: ScopeVisibility | None = None
    """可见范围（通配符时为 None）"""

    @classmethod
    def parse(cls, raw: str) -> 'Scope':
        """
        解析 scope 字符串。

        :param raw: ``files:read:own`` 或 ``files:*``
        :raises ValueError: 格式错误或枚举值无效
        """
        parts = raw.split(":")
        if len(parts) == 2:
            resource_str, action_str = parts
            if action_str != "*":
                raise ValueError(f"两段式 scope 的 action 必须是 '*': {raw}")
            return cls(
                resource=ScopeResource(resource_str),
                action=ScopeAction.WILDCARD,
                visibility=None,
            )
        elif len(parts) == 3:
            resource_str, action_str, visibility_str = parts
            if action_str == "*":
                raise ValueError(f"通配符 scope 不应有 visibility: {raw}")
            return cls(
                resource=ScopeResource(resource_str),
                action=ScopeAction(action_str),
                visibility=ScopeVisibility(visibility_str),
            )
        else:
            raise ValueError(f"无效的 scope 格式（需要 2 或 3 段）: {raw}")

    def matches(self, required: 'Scope') -> bool:
        """
        检查 self 是否满足 required 权限。

        匹配逻辑:
        - resource 必须相同
        - self.action == ``*`` 匹配任意 action
        - self.visibility == ``all`` 包含 ``own``
        """
        if self.resource != required.resource:
            return False

        if self.action == ScopeAction.WILDCARD:
            return True

        if self.action != required.action:
            return False

        if self.visibility == ScopeVisibility.ALL:
            return True

        return self.visibility == required.visibility

    def __str__(self) -> str:
        if self.action == ScopeAction.WILDCARD:
            return f"{self.resource}:*"
        return f"{self.resource}:{self.action}:{self.visibility}"


class ScopeSet(SQLModelBase):
    """scope 集合，支持批量权限检查"""

    scopes: list[Scope]
    """已持有的 scope 列表"""

    @classmethod
    def from_strings(cls, raw_list: 'list[str] | list[ScopeValueEnum]') -> 'ScopeSet':
        """从字符串列表构建 ScopeSet"""
        return cls(scopes=[Scope.parse(s) for s in raw_list])

    def has(self, required: str) -> bool:
        """
        检查集合中是否有 scope 满足 required。

        :param required: scope 字符串，如 ``files:read:own``
        """
        req = Scope.parse(required)
        return any(s.matches(req) for s in self.scopes)


# ==================== ScopeValueEnum（笛卡尔积自动生成） ====================

def _build_scope_value_members() -> dict[str, str]:
    """
    生成 resource × action × visibility 的笛卡尔积。

    通配符格式: ``files:*``（member name = ``files_wildcard``）
    完整格式: ``files:read:own``（member name = ``files_read_own``）
    """
    members: dict[str, str] = {}
    for resource in ScopeResource:
        # 通配符
        member_name = f"{resource.value.replace('.', '_')}_wildcard"
        members[member_name] = f"{resource.value}:*"
        # 完整格式
        for action in ScopeAction:
            if action == ScopeAction.WILDCARD:
                continue
            for visibility in ScopeVisibility:
                value = f"{resource.value}:{action.value}:{visibility.value}"
                member_name = f"{resource.value.replace('.', '_')}_{action.value}_{visibility.value}"
                members[member_name] = value
    return members


ScopeValueEnum = StrEnum('ScopeValueEnum', _build_scope_value_members())
"""
所有合法 scope 值的枚举（由笛卡尔积自动生成）。

用于 ``Array[ScopeValueEnum]`` 类型注解，提供 PG ENUM 级别的数据库校验。
"""


# ==================== 默认权限模板 ====================

USER_DEFAULT_SCOPES: list[ScopeValueEnum] = [
    ScopeValueEnum("files:create:own"),
    ScopeValueEnum("files:read:own"),
    ScopeValueEnum("files:write:own"),
    ScopeValueEnum("files:delete:own"),
    ScopeValueEnum("files:download:own"),
    ScopeValueEnum("shares:create:own"),
    ScopeValueEnum("shares:read:own"),
    ScopeValueEnum("shares:write:own"),
    ScopeValueEnum("shares:delete:own"),
    ScopeValueEnum("shares:download:own"),
]
"""注册会员默认权限"""

WEBDAV_SCOPES: list[ScopeValueEnum] = [
    ScopeValueEnum("webdav:create:own"),
    ScopeValueEnum("webdav:read:own"),
    ScopeValueEnum("webdav:write:own"),
    ScopeValueEnum("webdav:delete:own"),
]
"""WebDAV 权限（按需追加到用户组 default_scopes）"""

ARIA2_SCOPES: list[ScopeValueEnum] = [
    ScopeValueEnum("aria2:create:own"),
    ScopeValueEnum("aria2:read:own"),
    ScopeValueEnum("aria2:write:own"),
    ScopeValueEnum("aria2:delete:own"),
]
"""离线下载权限（按需追加到用户组 default_scopes）"""

ADMIN_SCOPES: list[ScopeValueEnum] = [
    ScopeValueEnum("files:*"),
    ScopeValueEnum("shares:*"),
    ScopeValueEnum("webdav:*"),
    ScopeValueEnum("aria2:*"),
    ScopeValueEnum("admin.users:*"),
    ScopeValueEnum("admin.groups:*"),
    ScopeValueEnum("admin.nodes:*"),
    ScopeValueEnum("admin.settings:*"),
    ScopeValueEnum("admin.policies:*"),
    ScopeValueEnum("admin.files:*"),
    ScopeValueEnum("admin.shares:*"),
    ScopeValueEnum("admin.tasks:*"),
    ScopeValueEnum("admin.file_apps:*"),
    ScopeValueEnum("admin.themes:*"),
    ScopeValueEnum("admin.dashboard:*"),
]
"""管理员默认权限（通配符）"""
