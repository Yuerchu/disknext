from enum import StrEnum
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, text, Index

from .base import SQLModelBase
from .mixin import TableBaseMixin

if TYPE_CHECKING:
    from .download import Download


class NodeStatus(StrEnum):
    """节点状态枚举"""
    ONLINE = "online"
    """正常"""
    OFFLINE = "offline"
    """离线"""


class NodeType(StrEnum):
    """节点类型枚举"""
    MASTER = "master"
    """主节点"""
    SLAVE = "slave"
    """从节点"""


class Aria2ConfigurationBase(SQLModelBase):
    """Aria2配置基础模型"""

    rpc_url: str | None = Field(default=None, max_length=255)
    """RPC地址"""

    rpc_secret: str | None = None
    """RPC密钥"""

    temp_path: str | None = Field(default=None, max_length=255)
    """临时下载路径"""

    max_concurrent: int = Field(default=5, ge=1, le=50)
    """最大并发数"""

    timeout: int = Field(default=300, ge=1)
    """请求超时时间（秒）"""


class Aria2Configuration(Aria2ConfigurationBase, TableBaseMixin):
    """Aria2配置模型（与Node一对一关联）"""

    node_id: int = Field(
        foreign_key="node.id",
        unique=True,
        index=True,
        ondelete="CASCADE"
    )
    """关联的节点ID"""

    # 反向关系
    node: "Node" = Relationship(back_populates="aria2_config")
    """关联的节点"""


class Node(SQLModelBase, TableBaseMixin):
    """节点模型"""

    __table_args__ = (
        Index("ix_node_status", "status"),
    )

    status: NodeStatus = Field(default=NodeStatus.ONLINE, sa_column_kwargs={"server_default": "'online'"})
    """节点状态"""

    name: str = Field(max_length=255, unique=True)
    """节点名称"""

    type: NodeType
    """节点类型"""

    server: str = Field(max_length=255)
    """节点地址（IP或域名）"""

    slave_key: str | None = Field(default=None, max_length=255)
    """从机通讯密钥"""

    master_key: str | None = Field(default=None, max_length=255)
    """主机通讯密钥"""

    aria2_enabled: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})
    """是否启用Aria2"""

    rank: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    """节点排序权重"""

    # 关系
    aria2_config: Aria2Configuration | None = Relationship(
        back_populates="node",
        sa_relationship_kwargs={"uselist": False, "cascade": "all, delete-orphan"},
    )
    """Aria2配置"""

    downloads: list["Download"] = Relationship(back_populates="node")
    """该节点的下载任务"""