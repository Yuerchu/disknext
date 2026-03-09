"""
对象元数据 KV 模型

以键值对形式存储文件的扩展元数据。键名使用命名空间前缀分类，
如 exif:width, stream:duration, music:artist 等。

架构：
    ObjectMetadata (KV 表，与 Object 一对多关系)
    └── 每个 Object 可以有多条元数据记录
    └── (object_id, name) 组合唯一索引

命名空间：
    - exif:    图片 EXIF 信息（尺寸、相机参数、拍摄时间等）
    - stream:  音视频流信息（时长、比特率、视频尺寸、编解码等）
    - music:   音乐标签（标题、艺术家、专辑等）
    - geo:     地理位置（经纬度、地址）
    - apk:     Android 安装包信息
    - custom:  用户自定义属性
    - sys:     系统内部元数据
    - thumb:   缩略图信息
"""
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlmodel import Field, UniqueConstraint, Index, Relationship

from sqlmodel_ext import SQLModelBase, UUIDTableBaseMixin, Str255

if TYPE_CHECKING:
    from .object import Object


# ==================== 枚举 ====================

class MetadataNamespace(StrEnum):
    """元数据命名空间枚举"""
    EXIF = "exif"
    """图片 EXIF 信息（含尺寸、相机参数、拍摄时间等）"""
    MUSIC = "music"
    """音乐标签（title/artist/album/genre 等）"""
    STREAM = "stream"
    """音视频流信息（codec/duration/bitrate/resolution 等）"""
    GEO = "geo"
    """地理位置（latitude/longitude/address）"""
    APK = "apk"
    """Android 安装包信息（package_name/version 等）"""
    THUMB = "thumb"
    """缩略图信息（内部使用）"""
    SYS = "sys"
    """系统元数据（内部使用）"""
    CUSTOM = "custom"
    """用户自定义属性"""


# 对外不可见的命名空间（API 不返回给普通用户）
INTERNAL_NAMESPACES: set[str] = {MetadataNamespace.SYS, MetadataNamespace.THUMB}

# 用户可写的命名空间
USER_WRITABLE_NAMESPACES: set[str] = {MetadataNamespace.CUSTOM}


# ==================== Base 模型 ====================

class ObjectMetadataBase(SQLModelBase):
    """对象元数据 KV 基础模型"""

    name: Str255
    """元数据键名，格式：namespace:key（如 exif:width, stream:duration）"""

    value: str
    """元数据值（统一为字符串存储）"""


# ==================== 数据库模型 ====================

class ObjectMetadata(ObjectMetadataBase, UUIDTableBaseMixin):
    """
    对象元数据 KV 模型

    以键值对形式存储文件的扩展元数据。键名使用命名空间前缀分类，
    每个对象的每个键名唯一（通过唯一索引保证）。
    """

    __table_args__ = (
        UniqueConstraint("object_id", "name", name="uq_object_metadata_object_name"),
        Index("ix_object_metadata_object_id", "object_id"),
    )

    object_id: UUID = Field(
        foreign_key="object.id",
        ondelete="CASCADE",
    )
    """关联的对象UUID"""

    is_public: bool = False
    """是否对分享页面公开"""

    # 关系
    object: "Object" = Relationship(back_populates="metadata_entries")
    """关联的对象"""


# ==================== DTO 模型 ====================

class MetadataResponse(SQLModelBase):
    """元数据查询响应 DTO"""

    metadatas: dict[str, str]
    """元数据字典（键名 → 值）"""


class MetadataPatchItem(SQLModelBase):
    """单条元数据补丁 DTO"""

    key: Str255
    """元数据键名"""

    value: str | None = None
    """值，None 表示删除此条目"""


class MetadataPatchRequest(SQLModelBase):
    """元数据批量更新请求 DTO"""

    patches: list[MetadataPatchItem]
    """补丁列表"""
