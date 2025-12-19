"""
通用响应模型定义
"""

from typing import Any
import uuid

from sqlmodel import Field

from .base import SQLModelBase

# [TODO] 未来把这拆了，直接按需返回状态码
class ResponseModel(SQLModelBase):
    """通用响应模型"""

    code: int = Field(default=0, ge=0, lt=60000)
    """系统内部状态码，0表示成功，其他表示失败"""

    data: Any = None
    """响应数据"""

    msg: str | None = None
    """响应消息，可以是错误消息或信息提示"""

    instance_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    """实例ID，用于标识请求的唯一性"""
