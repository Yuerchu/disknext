"""
WOPI（Web Application Open Platform Interface）协议模型

提供 WOPI CheckFileInfo 响应模型和 WOPI 访问令牌 Payload 定义。
"""
from uuid import UUID
from sqlmodel import Field

from sqlmodel_ext import SQLModelBase, Str64, Str255


class WopiFileInfo(SQLModelBase):
    """
    WOPI CheckFileInfo 响应模型。

    字段使用 serialization_alias 映射为 WOPI 规范的 PascalCase，
    序列化时调用 ``model_dump(by_alias=True)`` 即可。
    参考: https://learn.microsoft.com/en-us/microsoft-365/cloud-storage-partner-program/rest/files/checkfileinfo
    """

    base_file_name: Str255 = Field(serialization_alias="BaseFileName")
    """文件名（含扩展名）"""

    size: int = Field(serialization_alias="Size")
    """文件大小（字节）"""

    owner_id: Str64 = Field(serialization_alias="OwnerId")
    """文件所有者标识"""

    user_id: Str64 = Field(serialization_alias="UserId")
    """当前用户标识"""

    user_friendly_name: Str255 = Field(serialization_alias="UserFriendlyName")
    """用户显示名"""

    version: Str64 = Field(serialization_alias="Version")
    """文件版本标识（使用 updated_at）"""

    sha256: Str64 = Field(default="", serialization_alias="SHA256")
    """文件 SHA256 哈希（如果可用）"""

    user_can_write: bool = Field(default=False, serialization_alias="UserCanWrite")
    """用户是否可写"""

    user_can_not_write_relative: bool = Field(default=True, serialization_alias="UserCanNotWriteRelative")
    """是否禁止创建关联文件"""

    read_only: bool = Field(default=True, serialization_alias="ReadOnly")
    """文件是否只读"""

    supports_locks: bool = Field(default=False, serialization_alias="SupportsLocks")
    """是否支持锁（v1 不实现）"""

    supports_update: bool = Field(default=True, serialization_alias="SupportsUpdate")
    """是否支持更新"""

class WopiAccessTokenPayload(SQLModelBase):
    """WOPI 访问令牌内部 Payload"""

    file_id: UUID
    """文件UUID"""

    user_id: UUID
    """用户UUID"""

    can_write: bool = False
    """是否可写"""
