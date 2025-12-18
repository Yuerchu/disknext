
from typing import TYPE_CHECKING
from sqlmodel import Field, Relationship, text
from .base import TableBase

if TYPE_CHECKING:
    from .user import User


class GroupOptions(TableBase, table=True):
    """用户组选项模型"""

    group_id: int = Field(foreign_key="group.id", unique=True)
    """关联的用户组ID"""

    archive_download: bool = False
    """是否允许打包下载"""

    archive_task: bool = False
    """是否允许创建打包任务"""

    share_download: bool = False
    """是否允许分享下载"""

    share_free: bool = False
    """是否免积分分享"""

    webdav_proxy: bool = False
    """是否允许WebDAV代理"""

    aria2: bool = False
    """是否允许使用aria2"""

    relocate: bool = False
    """是否允许文件重定位"""

    source_batch: int = 10
    """批量获取源地址数量"""

    redirected_source: bool = False
    """是否使用重定向源"""

    available_nodes: str = "[]"
    """可用节点ID列表（JSON数组）"""

    select_node: bool = False
    """是否允许选择节点"""

    advance_delete: bool = False
    """是否允许高级删除"""

    # 反向关系
    group: "Group" = Relationship(back_populates="options")


class Group(TableBase, table=True):
    """用户组模型"""

    name: str = Field(max_length=255, unique=True)
    """用户组名"""

    policies: str | None = Field(default=None, max_length=255)
    """允许的策略ID列表，逗号分隔"""

    max_storage: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    """最大存储空间（字节）"""

    share_enabled: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})
    """是否允许创建分享"""

    web_dav_enabled: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})
    """是否允许使用WebDAV"""

    admin: bool = False
    """是否为管理员组"""

    speed_limit: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    """速度限制 (KB/s), 0为不限制"""

    # 一对一关系：用户组选项
    options: GroupOptions | None = Relationship(
        back_populates="group",
        sa_relationship_kwargs={"uselist": False}
    )

    # 关系：一个组可以有多个用户
    user: list["User"] = Relationship(
        back_populates="group",
        sa_relationship_kwargs={"foreign_keys": "User.group_id"}
    )
    previous_user: list["User"] = Relationship(
        back_populates="previous_group",
        sa_relationship_kwargs={"foreign_keys": "User.previous_group_id"}
    )
