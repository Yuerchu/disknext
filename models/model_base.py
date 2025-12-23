import uuid
from enum import StrEnum

from sqlmodel import Field

from .base import SQLModelBase

class MCPMethod(StrEnum):
    """MCP 方法枚举"""

    PING = "ping"
    """Ping 方法，用于测试连接"""

class MCPBase(SQLModelBase):
    """MCP 请求基础模型"""
    
    jsonrpc: str = "2.0"
    """JSON-RPC 版本"""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    """请求/响应 ID，用于标识请求/响应的唯一性"""

class MCPRequestBase(MCPBase):
    """MCP 请求模型基础类"""

    method: str
    """方法名称"""

class MCPResponseBase(MCPBase):
    """MCP 响应模型基础类"""

    result: str
    """方法返回结果"""

class ResponseBase(SQLModelBase):
    """通用响应模型"""

    instance_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    """实例ID，用于标识请求的唯一性"""