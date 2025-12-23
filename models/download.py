from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlmodel import Field, Relationship, UniqueConstraint, Index

from .base import SQLModelBase
from .mixin import UUIDTableBaseMixin, TableBaseMixin


class DownloadStatus(StrEnum):
    """下载状态枚举"""
    RUNNING = "running"
    """进行中"""
    COMPLETED = "completed"
    """已完成"""
    ERROR = "error"
    """错误"""


class DownloadType(StrEnum):
    """下载类型枚举"""
    # [TODO] 补充具体下载类型
    pass


if TYPE_CHECKING:
    from .user import User
    from .task import Task
    from .node import Node


# ==================== Aria2 信息模型 ====================

class DownloadAria2InfoBase(SQLModelBase):
    """Aria2下载信息基础模型"""

    info_hash: str | None = Field(default=None, max_length=40)
    """InfoHash（BT种子）"""

    piece_length: int = 0
    """分片大小"""

    num_pieces: int = 0
    """分片数量"""

    num_seeders: int = 0
    """做种人数"""

    connections: int = 0
    """连接数"""

    upload_speed: int = 0
    """上传速度（bytes/s）"""

    upload_length: int = 0
    """已上传大小（字节）"""

    error_code: str | None = None
    """错误代码"""

    error_message: str | None = None
    """错误信息"""


class DownloadAria2Info(DownloadAria2InfoBase, SQLModelBase, table=True):
    """Aria2下载信息模型（与Download一对一关联）"""

    download_id: UUID = Field(
        foreign_key="download.id",
        primary_key=True,
        ondelete="CASCADE"
    )
    """关联的下载任务UUID"""

    # 反向关系
    download: "Download" = Relationship(back_populates="aria2_info")
    """关联的下载任务"""


class DownloadAria2File(SQLModelBase, TableBaseMixin):
    """Aria2下载文件列表（与Download一对多关联）"""

    download_id: UUID = Field(
        foreign_key="download.id",
        index=True,
        ondelete="CASCADE"
    )
    """关联的下载任务UUID"""

    file_index: int = Field(ge=1)
    """文件索引（从1开始）"""

    path: str
    """文件路径"""

    length: int = 0
    """文件大小（字节）"""

    completed_length: int = 0
    """已完成大小（字节）"""

    is_selected: bool = True
    """是否选中下载"""

    # 反向关系
    download: "Download" = Relationship(back_populates="aria2_files")
    """关联的下载任务"""


# ==================== 主模型 ====================

class DownloadBase(SQLModelBase):
    pass

class Download(DownloadBase, UUIDTableBaseMixin):
    """离线下载任务模型"""

    __table_args__ = (
        UniqueConstraint("node_id", "g_id", name="uq_download_node_gid"),
        Index("ix_download_status", "status"),
        Index("ix_download_user_status", "user_id", "status"),
    )

    status: DownloadStatus = Field(default=DownloadStatus.RUNNING, sa_column_kwargs={"server_default": "'running'"})
    """下载状态"""

    type: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    """任务类型 [TODO] 待定义枚举"""

    source: str
    """来源URL或标识"""

    total_size: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    """总大小（字节）"""

    downloaded_size: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    """已下载大小（字节）"""

    g_id: str | None = Field(default=None, index=True)
    """Aria2 GID"""

    speed: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    """下载速度（bytes/s）"""

    parent: str | None = Field(default=None, max_length=255)
    """父任务标识"""

    error: str | None = Field(default=None)
    """错误信息"""

    dst: str
    """目标存储路径"""

    # 外键
    user_id: UUID = Field(
        foreign_key="user.id",
        index=True,
        ondelete="CASCADE"
    )
    """所属用户UUID"""

    task_id: int | None = Field(
        default=None,
        foreign_key="task.id",
        index=True,
        ondelete="SET NULL"
    )
    """关联的任务ID"""

    node_id: int = Field(
        foreign_key="node.id",
        index=True,
        ondelete="RESTRICT"
    )
    """执行下载的节点ID"""

    # 关系
    aria2_info: DownloadAria2Info | None = Relationship(
        back_populates="download",
        sa_relationship_kwargs={"uselist": False, "cascade": "all, delete-orphan"},
    )
    """Aria2下载信息"""

    aria2_files: list[DownloadAria2File] = Relationship(
        back_populates="download",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    """Aria2文件列表"""

    user: "User" = Relationship(back_populates="downloads")
    """所属用户"""

    task: "Task" = Relationship(back_populates="downloads")
    """关联的任务"""

    node: "Node" = Relationship(back_populates="downloads")
    """执行下载的节点"""
    
    