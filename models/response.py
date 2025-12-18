"""
通用响应模型定义
"""

from typing import Any
from uuid import uuid4

from sqlmodel import Field

from .base import SQLModelBase


class ResponseModel(SQLModelBase):
    """通用响应模型"""

    code: int = Field(default=0, ge=0, lt=60000)
    """系统内部状态码，0表示成功，其他表示失败"""

    data: dict[str, Any] | list[Any] | str | int | float | None = None
    """响应数据"""

    msg: str | None = None
    """响应消息，可以是错误消息或信息提示"""

    instance_id: str = Field(default_factory=lambda: str(uuid4()))
    """实例ID，用于标识请求的唯一性"""
