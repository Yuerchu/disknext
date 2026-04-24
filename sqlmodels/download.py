from enum import StrEnum
from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from sqlmodel import Field, Relationship, UniqueConstraint, Index

from sqlmodel_ext import SQLModelBase, UUIDTableBaseMixin, TableBaseMixin, Str64, Str255, HttpUrl

if TYPE_CHECKING:
    from .user import User
    from .task import Task
    from .node import Node

class DownloadStatus(StrEnum):
    """下载状态枚举"""
    PREPARING = "preparing"
    """准备中"""
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

    length: int = Field(ge=0)
    """文件大小（字节）"""

    completed_length: int = Field(ge=0)
    """已完成大小（字节）"""

    is_selected: bool = True
    """是否选中下载"""

    # 反向关系
    download: "Download" = Relationship(back_populates="aria2_files")
    """关联的下载任务"""

class Aria2TestRequest(SQLModelBase):
    """Aria2 测试请求 DTO"""

    rpc_url: HttpUrl = Field(max_length=255)
    """RPC 地址"""

    secret: str | None = None
    """RPC 密钥"""


# ==================== 主模型 ====================

class DownloadBase(SQLModelBase):
    """离线下载任务基础模型"""

class Download(DownloadBase, UUIDTableBaseMixin):
    """离线下载任务模型"""

    __table_args__ = (
        UniqueConstraint("node_id", "g_id", name="uq_download_node_gid"),
        Index("ix_download_user_status", "user_id", "status"),
    )

    status: DownloadStatus = Field(default=DownloadStatus.PREPARING, index=True)
    """下载状态"""

    type: int = Field(default=0)
    """任务类型 [TODO] 待定义枚举"""

    source: str
    """来源URL或标识"""

    total_size: int = Field(ge=0)
    """总大小（字节）"""

    downloaded_size: int = Field(ge=0)
    """已下载大小（字节）"""

    g_id: str | None = Field(default=None, index=True)
    """Aria2 GID"""

    speed: int = Field(ge=0)
    """下载速度（bytes/s）"""

    parent: Str255 | None = None
    """父任务标识"""

    error: str | None = Field(default=None)
    """错误信息"""

    dst: str = Field(max_length=255)
    """目标存储路径"""

    # Aria2 信息字段
    info_hash: Annotated[str | None, Field(max_length=40)] = None
    """InfoHash（BT种子）"""

    piece_length: int = Field(ge=0)
    """分片大小"""

    num_pieces: int = Field(ge=0)
    """分片数量"""

    num_seeders: int = Field(ge=0)
    """做种人数"""

    connections: int = Field(ge=0)
    """连接数"""

    upload_speed: int = Field(ge=0)
    """上传速度（bytes/s）"""

    upload_length: int = Field(ge=0)
    """已上传大小（字节）"""

    error_code: Str64 | None = None
    """Aria2 错误代码"""

    error_message: Str255 | None = None
    """Aria2 错误信息"""

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
    aria2_files: list[DownloadAria2File] = Relationship(back_populates="download", cascade_delete=True)
    """Aria2文件列表"""

    user: "User" = Relationship(back_populates="downloads")
    """所属用户"""

    task: "Task" = Relationship(back_populates="downloads")
    """关联的任务"""

    node: "Node" = Relationship(back_populates="downloads")
    """执行下载的节点"""
