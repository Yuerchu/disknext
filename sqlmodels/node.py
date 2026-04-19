from enum import StrEnum
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, Index

from sqlmodel_ext import SQLModelBase, TableBaseMixin, Str255

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


class Node(SQLModelBase, TableBaseMixin):
    """节点模型"""

    __table_args__ = (
        Index("ix_node_status", "status"),
    )

    status: NodeStatus = Field(default=NodeStatus.ONLINE)
    """节点状态"""

    name: Str255 = Field(unique=True)
    """节点名称"""

    type: NodeType
    """节点类型"""

    server: Str255
    """节点地址（IP或域名）"""

    slave_key: Str255 | None = None
    """从机通讯密钥"""

    master_key: Str255 | None = None
    """主机通讯密钥"""

    aria2_enabled: bool = False
    """是否启用Aria2"""

    rank: int = 0
    """节点排序权重"""

    # Aria2 配置字段（原 Aria2Configuration 表）
    aria2_rpc_url: Str255 | None = None
    """Aria2 RPC 地址"""

    aria2_rpc_secret: Str255 | None = None
    """Aria2 RPC 密钥"""

    aria2_temp_path: Str255 | None = None
    """Aria2 临时下载路径"""

    aria2_max_concurrent: int = Field(default=5, ge=1, le=50)
    """Aria2 最大并发数"""

    aria2_timeout: int = Field(default=300, ge=1)
    """Aria2 请求超时时间（秒）"""

    # 关系
    downloads: list["Download"] = Relationship(back_populates="node")
    """该节点的下载任务"""
