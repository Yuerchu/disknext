from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID
from datetime import datetime

from sqlmodel import Field, Relationship, CheckConstraint, Index

from .base import SQLModelBase
from .mixin import TableBaseMixin

if TYPE_CHECKING:
    from .user import User
    from .download import Download


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
    # [TODO] 补充具体任务类型
    pass


class TaskPropsBase(SQLModelBase):
    """任务属性基础模型"""

    source_path: str | None = None
    """源路径"""

    dest_path: str | None = None
    """目标路径"""

    file_ids: str | None = None
    """文件ID列表（逗号分隔）"""

    # [TODO] 根据业务需求补充更多字段


class TaskProps(TaskPropsBase, TableBaseMixin):
    """任务属性模型（与Task一对一关联）"""

    task_id: int = Field(
        foreign_key="task.id",
        primary_key=True,
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

    status: TaskStatus = Field(default=TaskStatus.QUEUED, sa_column_kwargs={"server_default": "'queued'"})
    """任务状态"""

    type: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    """任务类型 [TODO] 待定义枚举"""

    progress: int = Field(default=0, sa_column_kwargs={"server_default": "0"}, ge=0, le=100)
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
        sa_relationship_kwargs={"uselist": False, "cascade": "all, delete-orphan"},
    )
    """任务属性"""

    user: "User" = Relationship(back_populates="tasks")
    """所属用户"""

    downloads: list["Download"] = Relationship(back_populates="task")
    """关联的下载任务"""