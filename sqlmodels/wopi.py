"""
WOPI（Web Application Open Platform Interface）协议模型

提供 WOPI CheckFileInfo 响应模型和 WOPI 访问令牌 Payload 定义。
"""
from uuid import UUID

from sqlmodel_ext import SQLModelBase


class WopiFileInfo(SQLModelBase):
    """
    WOPI CheckFileInfo 响应模型。

    字段命名遵循 WOPI 规范（PascalCase），通过 alias 映射。
    参考: https://learn.microsoft.com/en-us/microsoft-365/cloud-storage-partner-program/rest/files/checkfileinfo
    """

    base_file_name: str
    """文件名（含扩展名）"""

    size: int
    """文件大小（字节）"""

    owner_id: str
    """文件所有者标识"""

    user_id: str
    """当前用户标识"""

    user_friendly_name: str
    """用户显示名"""

    version: str
    """文件版本标识（使用 updated_at）"""

    sha256: str = ""
    """文件 SHA256 哈希（如果可用）"""

    user_can_write: bool = False
    """用户是否可写"""

    user_can_not_write_relative: bool = True
    """是否禁止创建关联文件"""

    read_only: bool = True
    """文件是否只读"""

    supports_locks: bool = False
    """是否支持锁（v1 不实现）"""

    supports_update: bool = True
    """是否支持更新"""

    def to_wopi_dict(self) -> dict[str, str | int | bool]:
        """转换为 WOPI 规范的 PascalCase 字典"""
        return {
            "BaseFileName": self.base_file_name,
            "Size": self.size,
            "OwnerId": self.owner_id,
            "UserId": self.user_id,
            "UserFriendlyName": self.user_friendly_name,
            "Version": self.version,
            "SHA256": self.sha256,
            "UserCanWrite": self.user_can_write,
            "UserCanNotWriteRelative": self.user_can_not_write_relative,
            "ReadOnly": self.read_only,
            "SupportsLocks": self.supports_locks,
            "SupportsUpdate": self.supports_update,
        }


class WopiAccessTokenPayload(SQLModelBase):
    """WOPI 访问令牌内部 Payload"""

    file_id: UUID
    """文件UUID"""

    user_id: UUID
    """用户UUID"""

    can_write: bool = False
    """是否可写"""
