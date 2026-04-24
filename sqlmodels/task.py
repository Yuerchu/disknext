from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID
from datetime import datetime

from sqlmodel import Field, Relationship, CheckConstraint, Index

from sqlmodel_ext import SQLModelBase, TableBaseMixin, Str255, Str2048, Text2K, Text10K

if TYPE_CHECKING:
    from .download import Download
    from .user import User


class TaskStatus(StrEnum):
    """任务状态枚举"""
    QUEUED = "queued"
    """排队中"""
    RUNNING = "running"
    """处理中"""
    COMPLETED = "completed"
    """已完成"""
    ERROR = "error"
    """错误"""


class TaskType(StrEnum):
    """任务类型枚举"""
    POLICY_MIGRATE = "policy_migrate"
    """存储策略迁移"""


# ==================== DTO 模型 ====================


class TaskSummaryBase(SQLModelBase):
    """任务摘要基础字段"""

    id: int
    """任务ID"""

    type: TaskType
    """任务类型"""

    status: TaskStatus
    """任务状态"""

    progress: int
    """进度（0-100）"""

    error: Text2K | None
    """错误信息"""

    user_id: UUID
    """用户UUID"""

    created_at: datetime
    """创建时间"""

    updated_at: datetime
    """更新时间"""


class TaskSummary(TaskSummaryBase):
    """任务摘要，用于管理员列表展示"""

    username: Str255 | None
    """用户名"""



# ==================== 数据库模型 ====================


class TaskPropsBase(SQLModelBase):
    """任务属性基础模型"""

    source_path: Str2048 | None = None
    """源路径"""

    dest_path: Str2048 | None = None
    """目标路径"""

    file_ids: Text10K | None = None
    """文件ID列表（逗号分隔）"""

    source_policy_id: UUID | None = None
    """源存储策略UUID"""

    dest_policy_id: UUID | None = None
    """目标存储策略UUID"""

    object_id: UUID | None = None
    """关联的对象UUID"""


class TaskProps(TaskPropsBase, TableBaseMixin):
    """任务属性模型（与Task一对一关联）"""

    task_id: int = Field(
        foreign_key="task.id",
        unique=True,
        ondelete="CASCADE"
    )
    """关联的任务ID"""

    # 反向关系
    task: "Task" = Relationship(back_populates="props")
    """关联的任务"""


class Task(SQLModelBase, TableBaseMixin):
    """任务模型"""

    __table_args__ = (
        CheckConstraint("progress BETWEEN 0 AND 100", name="ck_task_progress_range"),
        Index("ix_task_status", "status"),
        Index("ix_task_user_status", "user_id", "status"),
    )

    status: TaskStatus = Field(default=TaskStatus.QUEUED)
    """任务状态"""

    type: TaskType
    """任务类型"""

    progress: int = Field(default=0, ge=0, le=100)
    """任务进度（0-100）"""

    error: str | None = Field(default=None)
    """错误信息"""

    # 外键
    user_id: UUID = Field(
        foreign_key="user.id",
        index=True,
        ondelete="CASCADE"
    )
    """所属用户UUID"""

    # 关系
    props: TaskProps | None = Relationship(
        back_populates="task",
        sa_relationship_kwargs={"uselist": False},
        cascade_delete=True,
    )
    """任务属性"""

    user: "User" = Relationship(back_populates="tasks")
    """所属用户"""

    downloads: list["Download"] = Relationship(back_populates="task")
    """关联的下载任务"""