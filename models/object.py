
from datetime import datetime
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from enum import StrEnum
from sqlmodel import Field, Relationship, UniqueConstraint, CheckConstraint, Index

from .base import SQLModelBase
from .mixin import UUIDTableBaseMixin

if TYPE_CHECKING:
    from .user import User
    from .policy import Policy
    from .source_link import SourceLink
    from .share import Share


class ObjectType(StrEnum):
    """对象类型枚举"""
    FILE = "file"
    FOLDER = "folder"
    
class StorageType(StrEnum):
    """存储类型枚举"""
    LOCAL = "local"
    QINIU = "qiniu"
    TENCENT = "tencent"
    ALIYUN = "aliyun"
    ONEDRIVE = "onedrive"
    GOOGLE_DRIVE = "google_drive"
    DROPBOX = "dropbox"
    WEBDAV = "webdav"
    REMOTE = "remote"


class FileMetadataBase(SQLModelBase):
    """文件元数据基础模型"""

    width: int | None = Field(default=None)
    """图片宽度（像素）"""

    height: int | None = Field(default=None)
    """图片高度（像素）"""

    duration: float | None = Field(default=None)
    """音视频时长（秒）"""

    bitrate: int | None = Field(default=None)
    """比特率（kbps）"""

    mime_type: str | None = Field(default=None, max_length=127)
    """MIME类型"""

    checksum_md5: str | None = Field(default=None, max_length=32)
    """MD5校验和"""

    checksum_sha256: str | None = Field(default=None, max_length=64)
    """SHA256校验和"""


# ==================== Base 模型 ====================

class ObjectBase(SQLModelBase):
    """对象基础字段，供数据库模型和 DTO 共享"""

    name: str
    """对象名称（文件名或目录名）"""

    type: ObjectType
    """对象类型：file 或 folder"""

    size: int = 0
    """文件大小（字节），目录为 0"""


# ==================== DTO 模型 ====================

class DirectoryCreateRequest(SQLModelBase):
    """创建目录请求 DTO"""

    parent_id: UUID
    """父目录UUID"""

    name: str
    """目录名称"""

    policy_id: UUID | None = None
    """存储策略UUID，不指定则继承父目录"""


class ObjectMoveRequest(SQLModelBase):
    """移动对象请求 DTO"""

    src_ids: list[UUID]
    """源对象UUID列表"""

    dst_id: UUID
    """目标文件夹UUID"""


class ObjectDeleteRequest(SQLModelBase):
    """删除对象请求 DTO"""

    ids: list[UUID]
    """待删除对象UUID列表"""


class ObjectResponse(ObjectBase):
    """对象响应 DTO"""

    id: UUID
    """对象UUID"""

    path: str
    """对象路径"""

    thumb: bool = False
    """是否有缩略图"""

    date: datetime
    """对象修改时间"""

    create_date: datetime
    """对象创建时间"""

    source_enabled: bool = False
    """是否启用离线下载源"""


class PolicyResponse(SQLModelBase):
    """存储策略响应 DTO"""

    id: UUID
    """策略UUID"""

    name: str
    """策略名称"""

    type: StorageType
    """存储类型"""

    max_size: int = Field(ge=0, default=0)
    """单文件最大限制，单位字节，0表示不限制"""

    file_type: list[str] | None = None
    """允许的文件类型列表，None 表示不限制"""


class DirectoryResponse(SQLModelBase):
    """目录响应 DTO"""

    id: UUID
    """当前目录UUID"""

    parent: UUID | None = None
    """父目录UUID，根目录为None"""

    objects: list[ObjectResponse] = []
    """目录下的对象列表"""

    policy: PolicyResponse
    """存储策略"""


# ==================== 数据库模型 ====================

class FileMetadata(FileMetadataBase, UUIDTableBaseMixin):
    """文件元数据模型（与Object一对一关联）"""

    object_id: UUID = Field(
        foreign_key="object.id",
        unique=True,
        index=True,
        ondelete="CASCADE"
    )
    """关联的对象UUID"""

    # 反向关系
    object: "Object" = Relationship(back_populates="file_metadata")
    """关联的对象"""


class Object(ObjectBase, UUIDTableBaseMixin):
    """
    统一对象模型

    合并了原有的 File 和 Folder 模型，通过 type 字段区分文件和目录。

    根目录规则：
    - 每个用户有一个显式根目录对象（name=用户的username, parent_id=NULL）
    - 用户创建的文件/文件夹的 parent_id 指向根目录或其他文件夹的 id
    - 根目录的 policy_id 指定用户默认存储策略
    - 路径格式：/username/path/to/file（如 /admin/docs/readme.md）
    """

    __table_args__ = (
        # 同一父目录下名称唯一（包括 parent_id 为 NULL 的情况）
        UniqueConstraint("owner_id", "parent_id", "name", name="uq_object_parent_name"),
        # 名称不能包含斜杠 ([TODO] 还有特殊字符)
        CheckConstraint(
            "name NOT LIKE '%/%' AND name NOT LIKE '%\\%'",
            name="ck_object_name_no_slash",
        ),
        # 性能索引
        Index("ix_object_owner_updated", "owner_id", "updated_at"),
        Index("ix_object_parent_updated", "parent_id", "updated_at"),
        Index("ix_object_owner_type", "owner_id", "type"),
        Index("ix_object_owner_size", "owner_id", "size"),
    )

    # ==================== 基础字段 ====================

    name: str = Field(max_length=255)
    """对象名称（文件名或目录名）"""

    type: ObjectType
    """对象类型：file 或 folder"""

    password: str | None = Field(default=None, max_length=255)
    """对象独立密码（仅当用户为对象单独设置密码时有效）"""

    # ==================== 文件专属字段 ====================

    source_name: str | None = Field(default=None, max_length=255)
    """源文件名（仅文件有效）"""

    size: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    """文件大小（字节），目录为 0"""

    upload_session_id: str | None = Field(default=None, max_length=255, unique=True, index=True)
    """分块上传会话ID（仅文件有效）"""

    # ==================== 外键 ====================

    parent_id: UUID | None = Field(
        default=None,
        foreign_key="object.id",
        index=True,
        ondelete="CASCADE"
    )
    """父目录UUID，NULL 表示这是用户的根目录"""

    owner_id: UUID = Field(
        foreign_key="user.id",
        index=True,
        ondelete="CASCADE"
    )
    """所有者用户UUID"""

    policy_id: UUID = Field(
        foreign_key="policy.id",
        index=True,
        ondelete="RESTRICT"
    )
    """存储策略UUID（文件直接使用，目录作为子文件的默认策略）"""

    # ==================== 关系 ====================

    owner: "User" = Relationship(back_populates="objects")
    """所有者"""

    policy: "Policy" = Relationship(back_populates="objects")
    """存储策略"""

    # 自引用关系
    parent: "Object" = Relationship(
        back_populates="children",
        sa_relationship_kwargs={"remote_side": "Object.id"},
    )
    """父目录"""

    children: list["Object"] = Relationship(
        back_populates="parent",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    """子对象（文件和子目录）"""

    # 仅文件有效的关系
    file_metadata: FileMetadata | None = Relationship(
        back_populates="object",
        sa_relationship_kwargs={"uselist": False, "cascade": "all, delete-orphan"},
    )
    """文件元数据（仅文件有效）"""

    source_links: list["SourceLink"] = Relationship(
        back_populates="object",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    """源链接列表（仅文件有效）"""

    shares: list["Share"] = Relationship(
        back_populates="object",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    """分享列表"""

    # ==================== 业务属性 ====================

    @property
    def is_file(self) -> bool:
        """是否为文件"""
        return self.type == ObjectType.FILE

    @property
    def is_folder(self) -> bool:
        """是否为目录"""
        return self.type == ObjectType.FOLDER

    # ==================== 业务方法 ====================

    @classmethod
    async def get_root(cls, session, user_id: UUID) -> "Object | None":
        """
        获取用户的根目录

        :param session: 数据库会话
        :param user_id: 用户UUID
        :return: 根目录对象，不存在则返回 None
        """
        return await cls.get(
            session,
            (cls.owner_id == user_id) & (cls.parent_id == None)
        )

    @classmethod
    async def get_by_path(
        cls,
        session,
        user_id: UUID,
        path: str,
        username: str,
    ) -> "Object | None":
        """
        根据路径获取对象

        :param session: 数据库会话
        :param user_id: 用户UUID
        :param path: 路径，如 "/username" 或 "/username/docs/images"
        :param username: 用户名，用于识别根目录
        :return: Object 或 None
        """
        path = path.strip()
        if not path:
            raise ValueError("路径不能为空")

        # 获取用户根目录
        root = await cls.get_root(session, user_id)
        if not root:
            return None

        # 移除开头的斜杠并分割路径
        if path.startswith("/"):
            path = path[1:]
        parts = [p for p in path.split("/") if p]

        # 空路径 -> 返回根目录
        if not parts:
            return root

        # 检查第一部分是否是用户名（根目录名）
        if parts[0] == username:
            # 路径以用户名开头，如 /admin/docs
            if len(parts) == 1:
                # 只有用户名，返回根目录
                return root
            # 去掉用户名部分，从第二个部分开始遍历
            parts = parts[1:]

        # 从根目录开始遍历剩余路径
        current = root
        for part in parts:
            if not current:
                return None

            current = await cls.get(
                session,
                (cls.owner_id == user_id) &
                (cls.parent_id == current.id) &
                (cls.name == part)
            )

        return current

    @classmethod
    async def get_children(cls, session, user_id: UUID, parent_id: UUID) -> list["Object"]:
        """
        获取目录下的所有子对象

        :param session: 数据库会话
        :param user_id: 用户UUID
        :param parent_id: 父目录UUID
        :return: 子对象列表
        """
        return await cls.get(
            session,
            (cls.owner_id == user_id) & (cls.parent_id == parent_id),
            fetch_mode="all"
        )
