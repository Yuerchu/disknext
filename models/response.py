"""
通用响应模型定义
"""

from typing import Any
import uuid

from sqlmodel import Field

from .base import SQLModelBase

# [TODO] 未来把这拆了，直接按需返回状态码
class ResponseBase(SQLModelBase):
    """通用响应模型"""

    instance_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    """实例ID，用于标识请求的唯一性"""
