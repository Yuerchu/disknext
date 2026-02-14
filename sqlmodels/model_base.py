import uuid
from datetime import datetime
from enum import StrEnum

from sqlmodel import Field

from sqlmodel_ext import SQLModelBase


class ResponseBase(SQLModelBase):
    """通用响应模型"""

    instance_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    """实例ID，用于标识请求的唯一性"""


# ==================== Admin Summary DTO ====================


class MetricsSummary(SQLModelBase):
    """站点统计摘要"""

    dates: list[datetime]
    """日期列表"""

    files: list[int]
    """每日新增文件数"""

    users: list[int]
    """每日新增用户数"""

    shares: list[int]
    """每日新增分享数"""

    file_total: int
    """文件总数"""

    user_total: int
    """用户总数"""

    share_total: int
    """分享总数"""

    entities_total: int
    """实体总数"""

    generated_at: datetime
    """生成时间"""


class LicenseInfo(SQLModelBase):
    """许可证信息"""

    expired_at: datetime
    """过期时间"""

    signed_at: datetime
    """签发时间"""

    root_domains: list[str]
    """根域名列表"""

    domains: list[str]
    """域名列表"""

    vol_domains: list[str]
    """卷域名列表"""


class VersionInfo(SQLModelBase):
    """版本信息"""

    version: str
    """版本号"""

    pro: bool
    """是否为专业版"""

    commit: str
    """提交哈希"""

class AdminSummaryResponse(ResponseBase):
    """管理员概况响应"""

    metrics_summary: MetricsSummary
    """统计摘要"""

    site_urls: list[str]
    """站点URL列表"""

    license: LicenseInfo
    """许可证信息"""

    version: VersionInfo
    """版本信息"""

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
    