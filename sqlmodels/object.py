
from datetime import datetime
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from enum import StrEnum
from sqlalchemy import BigInteger
from sqlmodel import Field, Relationship, CheckConstraint, Index, text

from sqlmodel_ext import SQLModelBase, UUIDTableBaseMixin

from .policy import PolicyType

if TYPE_CHECKING:
    from .user import User
    from .policy import Policy
    from .source_link import SourceLink
    from .share import Share
    from .physical_file import PhysicalFile
    from .uri import DiskNextURI
    from .object_metadata import ObjectMetadata


class ObjectType(StrEnum):
    """对象类型枚举"""
    FILE = "file"
    FOLDER = "folder"
    

# ==================== Base 模型 ====================

class ObjectBase(SQLModelBase):
    """对象基础字段，供数据库模型和 DTO 共享"""

    name: str
    """对象名称（文件名或目录名）"""

    type: ObjectType
    """对象类型"""

    size: int | None = None
    """文件大小（字节），目录为 None"""

    mime_type: str | None = Field(default=None, max_length=127)
    """MIME类型（仅文件有效）"""


# ==================== DTO 模型 ====================

class ObjectFileFinalize(SQLModelBase):
    """文件上传完成后更新 Object 的 DTO"""

    size: int
    """文件大小（字节）"""

    physical_file_id: UUID
    """关联的物理文件UUID"""


class ObjectMoveUpdate(SQLModelBase):
    """移动/重命名 Object 的 DTO"""

    parent_id: UUID
    """新的父目录UUID"""

    name: str
    """新名称"""


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

    thumb: bool = False
    """是否有缩略图"""

    created_at: datetime
    """对象创建时间"""

    updated_at: datetime
    """对象修改时间"""

    source_enabled: bool = False
    """是否启用离线下载源"""


class PolicyResponse(SQLModelBase):
    """存储策略响应 DTO"""

    id: UUID
    """策略UUID"""

    name: str
    """策略名称"""

    type: PolicyType
    """存储类型"""

    max_size: int = Field(ge=0, default=0, sa_type=BigInteger)
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

class Object(ObjectBase, UUIDTableBaseMixin):
    """
    统一对象模型

    合并了原有的 File 和 Folder 模型，通过 type 字段区分文件和目录。

    根目录规则：
    - 每个用户有一个显式根目录对象（name="/", parent_id=NULL）
    - 用户创建的文件/文件夹的 parent_id 指向根目录或其他文件夹的 id
    - 根目录的 policy_id 指定用户默认存储策略
    - 路径格式：/path/to/file（如 /docs/readme.md），不包含用户名前缀
    """

    __table_args__ = (
        # 同一父目录下名称唯一（仅对未删除记录生效）
        Index(
            "uq_object_parent_name_active",
            "owner_id", "parent_id", "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # 名称不能包含斜杠（根目录 parent_id IS NULL 除外，因为根目录 name="/"）
        CheckConstraint(
            "parent_id IS NULL OR (name NOT LIKE '%/%' AND name NOT LIKE '%\\%')",
            name="ck_object_name_no_slash",
        ),
        # 性能索引
        Index("ix_object_owner_updated", "owner_id", "updated_at"),
        Index("ix_object_parent_updated", "parent_id", "updated_at"),
        Index("ix_object_owner_type", "owner_id", "type"),
        Index("ix_object_owner_size", "owner_id", "size"),
        # 回收站查询索引
        Index("ix_object_owner_deleted", "owner_id", "deleted_at"),
    )

    # ==================== 基础字段 ====================

    name: str = Field(max_length=255)
    """对象名称（文件名或目录名）"""

    type: ObjectType
    """对象类型：file 或 folder"""

    password: str | None = Field(default=None, max_length=255)
    """对象独立密码（仅当用户为对象单独设置密码时有效）"""

    # ==================== 文件专属字段 ====================

    size: int = Field(default=0, sa_type=BigInteger, sa_column_kwargs={"server_default": "0"})
    """文件大小（字节），目录为 0"""

    upload_session_id: str | None = Field(default=None, max_length=255, unique=True, index=True)
    """分块上传会话ID（仅文件有效）"""

    physical_file_id: UUID | None = Field(
        default=None,
        foreign_key="physicalfile.id",
        index=True,
        ondelete="SET NULL"
    )
    """关联的物理文件UUID（仅文件有效，目录为NULL）"""

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

    # ==================== 封禁相关字段 ====================

    is_banned: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})
    """是否被封禁"""

    banned_at: datetime | None = None
    """封禁时间"""

    banned_by: UUID | None = Field(
        default=None,
        foreign_key="user.id",
        index=True,
        ondelete="SET NULL",
        sa_column_kwargs={"name": "banned_by"}
    )
    """封禁操作者UUID"""

    ban_reason: str | None = Field(default=None, max_length=500)
    """封禁原因"""

    # ==================== 软删除相关字段 ====================

    deleted_at: datetime | None = Field(default=None, index=True)
    """软删除时间戳，NULL 表示未删除"""

    deleted_original_parent_id: UUID | None = Field(
        default=None,
        foreign_key="object.id",
        ondelete="SET NULL",
    )
    """软删除前的原始父目录UUID（恢复时用于还原位置）"""

    # ==================== 关系 ====================

    owner: "User" = Relationship(
        back_populates="objects",
        sa_relationship_kwargs={"foreign_keys": "[Object.owner_id]"}
    )
    """所有者"""

    banner: "User" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[Object.banned_by]"}
    )
    """封禁操作者"""

    policy: "Policy" = Relationship(back_populates="objects")
    """存储策略"""

    # 自引用关系
    parent: "Object" = Relationship(
        back_populates="children",
        sa_relationship_kwargs={
            "remote_side": "Object.id",
            "foreign_keys": "[Object.parent_id]",
        },
    )
    """父目录"""

    children: list["Object"] = Relationship(
        back_populates="parent",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "foreign_keys": "[Object.parent_id]",
        },
    )
    """子对象（文件和子目录）"""

    # 仅文件有效的关系
    metadata_entries: list["ObjectMetadata"] = Relationship(
        back_populates="object",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    """元数据键值对列表"""

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

    physical_file: "PhysicalFile" = Relationship(back_populates="objects")
    """关联的物理文件（仅文件有效）"""

    # ==================== 业务属性 ====================

    @property
    def source_name(self) -> str | None:
        """
        源文件存储路径（向后兼容属性）

        :return: 物理文件存储路径，如果没有关联物理文件则返回 None
        """
        if self.physical_file:
            return self.physical_file.storage_path
        return None

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
            (cls.owner_id == user_id) & (cls.parent_id == None) & (cls.deleted_at == None)
        )

    @classmethod
    async def get_by_path(
        cls,
        session,
        user_id: UUID,
        path: str,
    ) -> "Object | None":
        """
        根据路径获取对象

        路径从用户根目录开始，不包含用户名前缀。
        如 "/" 表示根目录，"/docs/images" 表示根目录下的 docs/images。

        :param session: 数据库会话
        :param user_id: 用户UUID
        :param path: 路径，如 "/" 或 "/docs/images"
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

        # 从根目录开始遍历路径
        current = root
        for part in parts:
            if not current:
                return None

            current = await cls.get(
                session,
                (cls.owner_id == user_id) &
                (cls.parent_id == current.id) &
                (cls.name == part) &
                (cls.deleted_at == None)
            )

        return current

    @classmethod
    async def get_children(cls, session, user_id: UUID, parent_id: UUID) -> list["Object"]:
        """
        获取目录下的所有子对象（不包含已软删除的）

        :param session: 数据库会话
        :param user_id: 用户UUID
        :param parent_id: 父目录UUID
        :return: 子对象列表
        """
        return await cls.get(
            session,
            (cls.owner_id == user_id) & (cls.parent_id == parent_id) & (cls.deleted_at == None),
            fetch_mode="all"
        )

    @classmethod
    async def get_all_children(cls, session, user_id: UUID, parent_id: UUID) -> list["Object"]:
        """
        获取目录下的所有子对象（包含已软删除的，用于永久删除场景）

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

    @classmethod
    async def get_trash_items(cls, session, user_id: UUID) -> list["Object"]:
        """
        获取用户回收站中的顶层对象

        只返回被直接软删除的顶层对象（deleted_at 非 NULL），
        不返回其子对象（子对象的 deleted_at 为 NULL，通过 parent 关系间接处于回收站中）。

        :param session: 数据库会话
        :param user_id: 用户UUID
        :return: 回收站顶层对象列表
        """
        return await cls.get(
            session,
            (cls.owner_id == user_id) & (cls.deleted_at != None),
            fetch_mode="all"
        )

    @classmethod
    async def resolve_uri(
        cls,
        session,
        uri: "DiskNextURI",
        requesting_user_id: UUID | None = None,
    ) -> "Object":
        """
        将 URI 解析为 Object 实例

        分派逻辑（类似 Cloudreve 的 getNavigator）：
        - MY    → user_id = uri.id(str(requesting_user_id))
                  验证权限（自己的或管理员），然后 get_by_path
        - SHARE → 通过 uri.fs_id 查 Share 表，验证密码和有效期
                  获取 share.object，然后沿 uri.path 遍历子对象
        - TRASH → 延后实现

        :param session: 数据库会话
        :param uri: DiskNextURI 实例
        :param requesting_user_id: 请求用户UUID
        :return: Object 实例
        :raises ValueError: URI 无法解析
        :raises PermissionError: 权限不足
        :raises NotImplementedError: 不支持的命名空间
        """
        from .uri import FileSystemNamespace

        if uri.namespace == FileSystemNamespace.MY:
            # 确定目标用户
            target_user_id_str = uri.id(str(requesting_user_id) if requesting_user_id else None)
            if not target_user_id_str:
                raise ValueError("MY 命名空间需要提供 fs_id 或 requesting_user_id")

            target_user_id = UUID(target_user_id_str)

            # 权限检查：只能访问自己的空间（管理员权限由路由层判断）
            if requesting_user_id and target_user_id != requesting_user_id:
                raise PermissionError("无权访问其他用户的文件空间")

            obj = await cls.get_by_path(session, target_user_id, uri.path)
            if not obj:
                raise ValueError(f"路径不存在: {uri.path}")
            return obj

        elif uri.namespace == FileSystemNamespace.SHARE:
            raise NotImplementedError("分享空间解析尚未实现")

        elif uri.namespace == FileSystemNamespace.TRASH:
            raise NotImplementedError("回收站解析尚未实现")

        else:
            raise ValueError(f"未知的命名空间: {uri.namespace}")

    async def get_full_path(self, session) -> str:
        """
        从当前对象沿 parent_id 向上遍历到根目录，返回完整路径

        :param session: 数据库会话
        :return: 完整路径，如 "/docs/images/photo.jpg"
        """
        parts: list[str] = []
        current: Object | None = self

        while current and current.parent_id is not None:
            parts.append(current.name)
            current = await Object.get(session, Object.id == current.parent_id)

        # 反转顺序（从根到当前）
        parts.reverse()
        return "/" + "/".join(parts)


# ==================== 上传会话模型 ====================

class UploadSessionBase(SQLModelBase):
    """上传会话基础字段"""

    file_name: str = Field(max_length=255)
    """原始文件名"""

    file_size: int = Field(ge=0, sa_type=BigInteger)
    """文件总大小（字节）"""

    chunk_size: int = Field(ge=1, sa_type=BigInteger)
    """分片大小（字节）"""

    total_chunks: int = Field(ge=1)
    """总分片数"""


class UploadSession(UploadSessionBase, UUIDTableBaseMixin):
    """
    上传会话模型

    用于管理分片上传的会话状态。
    会话有效期为24小时，过期后自动失效。
    """

    # 会话状态
    uploaded_chunks: int = 0
    """已上传分片数"""

    uploaded_size: int = Field(default=0, sa_type=BigInteger)
    """已上传大小（字节）"""

    storage_path: str | None = Field(default=None, max_length=512)
    """文件存储路径"""

    s3_upload_id: str | None = Field(default=None, max_length=256)
    """S3 Multipart Upload ID（仅 S3 策略使用）"""

    s3_part_etags: str | None = None
    """S3 已上传分片的 ETag 列表，JSON 格式 [[1,"etag1"],[2,"etag2"]]（仅 S3 策略使用）"""

    expires_at: datetime
    """会话过期时间"""

    # 外键
    owner_id: UUID = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    """上传者用户UUID"""

    parent_id: UUID = Field(foreign_key="object.id", index=True, ondelete="CASCADE")
    """目标父目录UUID"""

    policy_id: UUID = Field(foreign_key="policy.id", index=True, ondelete="RESTRICT")
    """存储策略UUID"""

    # 关系
    owner: "User" = Relationship()
    """上传者"""

    parent: "Object" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[UploadSession.parent_id]"}
    )
    """目标父目录"""

    policy: "Policy" = Relationship()
    """存储策略"""

    @property
    def is_expired(self) -> bool:
        """会话是否已过期"""
        return datetime.now() > self.expires_at

    @property
    def is_complete(self) -> bool:
        """上传是否完成"""
        return self.uploaded_chunks >= self.total_chunks


# ==================== 上传会话相关 DTO ====================

class CreateUploadSessionRequest(SQLModelBase):
    """创建上传会话请求 DTO"""

    file_name: str = Field(max_length=255)
    """文件名"""

    file_size: int = Field(ge=0)
    """文件大小（字节）"""

    parent_id: UUID
    """父目录UUID"""

    policy_id: UUID | None = None
    """存储策略UUID，不指定则使用父目录的策略"""


class UploadSessionResponse(SQLModelBase):
    """上传会话响应 DTO"""

    id: UUID
    """会话UUID"""

    file_name: str
    """原始文件名"""

    file_size: int
    """文件总大小（字节）"""

    chunk_size: int
    """分片大小（字节）"""

    total_chunks: int
    """总分片数"""

    uploaded_chunks: int
    """已上传分片数"""

    expires_at: datetime
    """过期时间"""


class UploadChunkResponse(SQLModelBase):
    """上传分片响应 DTO"""

    uploaded_chunks: int
    """已上传分片数"""

    total_chunks: int
    """总分片数"""

    is_complete: bool
    """是否上传完成"""

    object_id: UUID | None = None
    """完成后的文件对象UUID，未完成时为None"""


class CreateFileRequest(SQLModelBase):
    """创建空白文件请求 DTO"""

    name: str = Field(max_length=255)
    """文件名"""

    parent_id: UUID
    """父目录UUID"""

    policy_id: UUID | None = None
    """存储策略UUID，不指定则使用父目录的策略"""


class ObjectSwitchPolicyRequest(SQLModelBase):
    """切换对象存储策略请求"""

    policy_id: UUID
    """目标存储策略UUID"""

    is_migrate_existing: bool = False
    """（仅目录）是否迁移已有文件，默认 false 只影响新文件"""


# ==================== 对象操作相关 DTO ====================

class ObjectCopyRequest(SQLModelBase):
    """复制对象请求 DTO"""

    src_ids: list[UUID]
    """源对象UUID列表"""

    dst_id: UUID
    """目标文件夹UUID"""


class ObjectRenameRequest(SQLModelBase):
    """重命名对象请求 DTO"""

    id: UUID
    """对象UUID"""

    new_name: str = Field(max_length=255)
    """新名称"""


class ObjectPropertyResponse(SQLModelBase):
    """对象基本属性响应 DTO"""

    id: UUID
    """对象UUID"""

    name: str
    """对象名称"""

    type: ObjectType
    """对象类型"""

    size: int
    """文件大小（字节）"""

    mime_type: str | None = None
    """MIME类型"""

    created_at: datetime
    """创建时间"""

    updated_at: datetime
    """修改时间"""

    parent_id: UUID | None
    """父目录UUID"""


class ObjectPropertyDetailResponse(ObjectPropertyResponse):
    """对象详细属性响应 DTO（继承基本属性）"""

    # 校验和（从 PhysicalFile 读取）
    checksum_md5: str | None = None
    """MD5校验和"""

    checksum_sha256: str | None = None
    """SHA256校验和"""

    # 分享统计
    share_count: int = 0
    """分享次数"""

    total_views: int = 0
    """总浏览次数"""

    total_downloads: int = 0
    """总下载次数"""

    # 存储信息
    policy_name: str | None = None
    """存储策略名称"""

    reference_count: int = 1
    """物理文件引用计数（仅文件有效）"""

    # 元数据（KV 格式）
    metadatas: dict[str, str] = {}
    """所有元数据条目（键名 → 值）"""


# ==================== 管理员文件管理 DTO ====================

class AdminFileResponse(ObjectResponse):
    """管理员文件响应 DTO"""

    owner_id: UUID
    """所有者UUID"""

    owner_email: str
    """所有者邮箱"""

    policy_name: str
    """存储策略名称"""

    is_banned: bool = False
    """是否被封禁"""

    banned_at: datetime | None = None
    """封禁时间"""

    ban_reason: str | None = None
    """封禁原因"""

    @classmethod
    def from_object(
        cls,
        obj: "Object",
        owner: "User | None",
        policy: "Policy | None",
    ) -> "AdminFileResponse":
        """从 Object ORM 对象构建"""
        return cls(
            # ObjectBase 字段
            **ObjectBase.model_validate(obj, from_attributes=True).model_dump(),
            # ObjectResponse 字段
            id=obj.id,
            thumb=False,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
            source_enabled=False,
            # AdminFileResponse 字段
            owner_id=obj.owner_id,
            owner_email=owner.email if owner else "unknown",
            policy_name=policy.name if policy else "unknown",
            is_banned=obj.is_banned,
            banned_at=obj.banned_at,
            ban_reason=obj.ban_reason,
        )


class FileBanRequest(SQLModelBase):
    """文件封禁请求 DTO"""

    ban: bool = True
    """是否封禁"""

    reason: str | None = Field(default=None, max_length=500)
    """封禁原因"""


class AdminFileListResponse(SQLModelBase):
    """管理员文件列表响应 DTO"""

    files: list[AdminFileResponse] = []
    """文件列表"""

    total: int = 0
    """总数"""


# ==================== 回收站相关 DTO ====================

class TrashItemResponse(SQLModelBase):
    """回收站对象响应 DTO"""

    id: UUID
    """对象UUID"""

    name: str
    """对象名称"""

    type: ObjectType
    """对象类型"""

    size: int
    """文件大小（字节）"""

    deleted_at: datetime
    """删除时间"""

    original_parent_id: UUID | None
    """原始父目录UUID"""


class TrashRestoreRequest(SQLModelBase):
    """恢复对象请求 DTO"""

    ids: list[UUID]
    """待恢复对象UUID列表"""


class TrashDeleteRequest(SQLModelBase):
    """永久删除对象请求 DTO"""

    ids: list[UUID]
    """待永久删除对象UUID列表"""
