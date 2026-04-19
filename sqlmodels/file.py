
from datetime import datetime
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from enum import StrEnum
from loguru import logger as l
from sqlmodel import Field, Relationship, CheckConstraint, Index, text
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodel_ext import SQLModelBase, UUIDTableBaseMixin, NonNegativeBigInt, PositiveBigInt, Str24, Str64, Str128, Str255, Str256

from .policy import PolicyType

from .physical_file import PhysicalFile
from .user import User

if TYPE_CHECKING:
    from .policy import Policy
    from .source_link import SourceLink
    from .share import Share
    from .uri import DiskNextURI
    from .file_metadata import FileMetadata


class FileType(StrEnum):
    """文件类型枚举"""
    FILE = "file"
    FOLDER = "folder"


class FileCategory(StrEnum):
    """文件类型分类枚举，用于按类别筛选文件"""
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"


# ==================== Base 模型 ====================

class FileBase(SQLModelBase):
    """对象基础字段，供数据库模型和 DTO 共享"""

    name: str = Field(min_length=1, max_length=255)
    """对象名称（文件名或目录名）"""

    type: FileType
    """对象类型"""

    size: int | None = None
    """文件大小（字节），目录为 None"""

    mime_type: str | None = Field(default=None, max_length=127)
    """MIME类型（仅文件有效）"""


# ==================== DTO 模型 ====================

class FileFinalize(SQLModelBase):
    """文件上传完成后更新 Object 的 DTO"""

    size: int
    """文件大小（字节）"""

    physical_file_id: UUID
    """关联的物理文件UUID"""


class FileMoveUpdate(SQLModelBase):
    """移动/重命名 Object 的 DTO"""

    parent_id: UUID
    """新的父目录UUID"""

    name: str = Field(min_length=1, max_length=255)
    """新名称"""


class DirectoryCreateRequest(SQLModelBase):
    """创建目录请求 DTO"""

    parent_id: UUID
    """父目录UUID"""

    name: str = Field(min_length=1, max_length=255)
    """目录名称"""

    policy_id: UUID | None = None
    """存储策略UUID，不指定则继承父目录"""


class FileMoveRequest(SQLModelBase):
    """移动对象请求 DTO"""

    src_ids: list[UUID] = Field(min_length=1, max_length=100)
    """源对象UUID列表"""

    dst_id: UUID
    """目标文件夹UUID"""


class FileDeleteRequest(SQLModelBase):
    """删除对象请求 DTO"""

    ids: list[UUID] = Field(min_length=1, max_length=100)
    """待删除对象UUID列表"""


class FileResponse(FileBase):
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

    name: Str255
    """策略名称"""

    type: PolicyType
    """存储类型"""

    max_size: NonNegativeBigInt = 0
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

class File(FileBase, UUIDTableBaseMixin):
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
            "uq_file_parent_name_active",
            "owner_id", "parent_id", "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # 名称不能包含斜杠（根目录 parent_id IS NULL 除外，因为根目录 name="/"）
        CheckConstraint(
            "parent_id IS NULL OR (name NOT LIKE '%/%' AND name NOT LIKE '%\\%')",
            name="ck_file_name_no_slash",
        ),
        # 性能索引
        Index("ix_file_owner_updated", "owner_id", "updated_at"),
        Index("ix_file_parent_updated", "parent_id", "updated_at"),
        Index("ix_file_owner_type", "owner_id", "type"),
        Index("ix_file_owner_size", "owner_id", "size"),
        # 回收站查询索引
        Index("ix_file_owner_deleted", "owner_id", "deleted_at"),
    )

    # ==================== 基础字段 ====================

    name: Str255
    """对象名称（文件名或目录名）"""

    type: FileType
    """对象类型：file 或 folder"""

    password: Str255 | None = None
    """对象独立密码（仅当用户为对象单独设置密码时有效）"""

    # ==================== 文件专属字段 ====================

    size: NonNegativeBigInt = 0
    """文件大小（字节），目录为 0"""

    upload_session_id: Str255 | None = Field(default=None, unique=True, index=True)
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
        foreign_key="file.id",
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

    is_banned: bool = False
    """是否被封禁"""

    banned_at: datetime | None = None
    """封禁时间"""

    banned_by: UUID | None = Field(
        default=None,
        foreign_key="user.id",
        index=True,
        ondelete="SET NULL",
    )
    """封禁操作者UUID"""

    ban_reason: str | None = Field(default=None, max_length=500)
    """封禁原因"""

    # ==================== 软删除相关字段 ====================

    deleted_at: datetime | None = Field(default=None, index=True)
    """软删除时间戳，NULL 表示未删除"""

    deleted_original_parent_id: UUID | None = Field(
        default=None,
        foreign_key="file.id",
        ondelete="SET NULL",
    )
    """软删除前的原始父目录UUID（恢复时用于还原位置）"""

    # ==================== 关系 ====================

    owner: "User" = Relationship(
        back_populates="files",
        sa_relationship_kwargs={"foreign_keys": "[File.owner_id]"}
    )
    """所有者"""

    banner: "User" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[File.banned_by]"}
    )
    """封禁操作者"""

    policy: "Policy" = Relationship(back_populates="files")
    """存储策略"""

    # 自引用关系
    parent: "File" = Relationship(
        back_populates="children",
        sa_relationship_kwargs={
            "remote_side": "File.id",
            "foreign_keys": "[File.parent_id]",
        },
    )
    """父目录"""

    children: list["File"] = Relationship(
        back_populates="parent",
        cascade_delete=True,
        sa_relationship_kwargs={"foreign_keys": "[File.parent_id]"},
    )
    """子对象（文件和子目录）"""

    # 仅文件有效的关系
    metadata_entries: list["FileMetadata"] = Relationship(back_populates="file", cascade_delete=True)
    """元数据键值对列表"""

    source_links: list["SourceLink"] = Relationship(back_populates="file", cascade_delete=True)
    """源链接列表（仅文件有效）"""

    shares: list["Share"] = Relationship(back_populates="file", cascade_delete=True)
    """分享列表"""

    physical_file: "PhysicalFile" = Relationship(back_populates="files")
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
        return self.type == FileType.FILE

    @property
    def is_folder(self) -> bool:
        """是否为目录"""
        return self.type == FileType.FOLDER

    # ==================== 验证方法 ====================

    @staticmethod
    def validate_name(name: str) -> str:
        """
        验证文件/目录名：非空 + 无斜杠。返回 strip 后的名称。

        :param name: 原始名称
        :return: strip 后的合法名称
        :raises HTTPException: 400 名称无效
        """
        from fastapi import HTTPException

        stripped = name.strip() if name else ""
        if not stripped:
            raise HTTPException(status_code=400, detail="名称不能为空")
        if '/' in stripped or '\\' in stripped:
            raise HTTPException(status_code=400, detail="名称不能包含斜杠")
        return stripped

    @classmethod
    async def validate_parent(
        cls,
        session: AsyncSession,
        parent_id: UUID,
        owner_id: UUID,
    ) -> "File":
        """
        验证父目录：存在 + 属于用户 + 是目录 + 未封禁 + 未删除

        :param session: 数据库会话
        :param parent_id: 父目录UUID
        :param owner_id: 当前用户UUID
        :return: 验证通过的父目录对象
        :raises HTTPException: 404/400/403
        """
        from fastapi import HTTPException
        from utils import http_exceptions

        parent = await cls.get(
            session,
            (cls.id == parent_id) & (cls.deleted_at == None)
        )
        if not parent or parent.owner_id != owner_id:
            raise HTTPException(status_code=404, detail="父目录不存在")
        if not parent.is_folder:
            raise HTTPException(status_code=400, detail="父对象不是目录")
        if parent.is_banned:
            http_exceptions.raise_banned("目标目录已被封禁，无法执行此操作")
        return parent

    @classmethod
    async def check_name_conflict(
        cls,
        session: AsyncSession,
        owner_id: UUID,
        parent_id: UUID,
        name: str,
    ) -> None:
        """
        检查同目录下是否存在同名对象（仅未删除的）

        :param session: 数据库会话
        :param owner_id: 用户UUID
        :param parent_id: 父目录UUID
        :param name: 对象名称
        :raises HTTPException: 409 同名对象已存在
        """
        from fastapi import HTTPException

        existing = await cls.get(
            session,
            (cls.owner_id == owner_id) &
            (cls.parent_id == parent_id) &
            (cls.name == name) &
            (cls.deleted_at == None)
        )
        if existing:
            raise HTTPException(status_code=409, detail="同名文件或目录已存在")

    # ==================== 业务方法 ====================

    @classmethod
    async def get_root(cls, session, user_id: UUID) -> "File | None":
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
    ) -> "File | None":
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
    async def get_children(cls, session, user_id: UUID, parent_id: UUID) -> list["File"]:
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
    async def get_all_children(cls, session, user_id: UUID, parent_id: UUID) -> list["File"]:
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
    async def get_trash_items(cls, session, user_id: UUID) -> list["File"]:
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
    async def get_by_category(
        cls,
        session: 'AsyncSession',
        user_id: UUID,
        extensions: list[str],
        table_view: 'TableViewRequest | None' = None,
    ) -> 'ListResponse[Object]':
        """
        按扩展名列表查询用户的所有文件（跨目录）

        只查询未删除、未封禁的文件对象，使用 ILIKE 匹配文件名后缀。

        :param session: 数据库会话
        :param user_id: 用户UUID
        :param extensions: 扩展名列表（不含点号）
        :param table_view: 分页排序参数
        :return: 分页文件列表
        """
        from sqlalchemy import or_

        ext_conditions = [cls.name.ilike(f"%.{ext}") for ext in extensions]
        condition = (
            (cls.owner_id == user_id) &
            (cls.type == FileType.FILE) &
            (cls.deleted_at == None) &
            (cls.is_banned == False) &
            or_(*ext_conditions)
        )
        return await cls.get_with_count(session, condition, table_view=table_view)

    @classmethod
    async def resolve_uri(
        cls,
        session,
        uri: "DiskNextURI",
        requesting_user_id: UUID | None = None,
    ) -> "File":
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
        current: File | None = self

        while current and current.parent_id is not None:
            parts.append(current.name)
            current = await File.get(session, File.id == current.parent_id)

        # 反转顺序（从根到当前）
        parts.reverse()
        return "/" + "/".join(parts)

    # ==================== 软删除 ====================

    @classmethod
    async def soft_delete_batch(
        cls,
        session: AsyncSession,
        objects: list["File"],
    ) -> int:
        """
        批量软删除对象

        只标记顶层对象：设置 deleted_at、保存原 parent_id 到 deleted_original_parent_id、
        将 parent_id 置 NULL 脱离文件树。子对象保持不变，物理文件不移动。

        :param session: 数据库会话
        :param objects: 待软删除的对象列表
        :return: 软删除的对象数量
        """
        deleted_count = 0
        now = datetime.now()

        for obj in objects:
            obj.deleted_at = now
            obj.deleted_original_parent_id = obj.parent_id
            obj.parent_id = None
            await obj.save(session, commit=False, refresh=False)
            deleted_count += 1

        await session.commit()
        return deleted_count

    # ==================== 恢复 ====================

    @classmethod
    async def _resolve_name_conflict(
        cls,
        session: AsyncSession,
        user_id: UUID,
        parent_id: UUID,
        name: str,
    ) -> str:
        """
        解决同名冲突，返回不冲突的名称

        命名规则：原名称 → 原名称 (1) → 原名称 (2) → ...
        对于有扩展名的文件：name.ext → name (1).ext → name (2).ext → ...

        :param session: 数据库会话
        :param user_id: 用户UUID
        :param parent_id: 父目录UUID
        :param name: 原始名称
        :return: 不冲突的名称
        """
        existing = await cls.get(
            session,
            (cls.owner_id == user_id) &
            (cls.parent_id == parent_id) &
            (cls.name == name) &
            (cls.deleted_at == None)
        )
        if not existing:
            return name

        # 分离文件名和扩展名
        if '.' in name:
            base, ext = name.rsplit('.', 1)
            ext = f".{ext}"
        else:
            base = name
            ext = ""

        counter = 1
        while True:
            new_name = f"{base} ({counter}){ext}"
            existing = await cls.get(
                session,
                (cls.owner_id == user_id) &
                (cls.parent_id == parent_id) &
                (cls.name == new_name) &
                (cls.deleted_at == None)
            )
            if not existing:
                return new_name
            counter += 1

    @classmethod
    async def restore_batch(
        cls,
        session: AsyncSession,
        objects: list["File"],
        user_id: UUID,
    ) -> int:
        """
        从回收站批量恢复对象

        检查原父目录是否存在且未删除：
        - 存在 → 恢复到原位置
        - 不存在 → 恢复到用户根目录
        处理同名冲突（自动重命名）。

        :param session: 数据库会话
        :param objects: 待恢复的对象列表（必须是回收站中的顶层对象）
        :param user_id: 用户UUID
        :return: 恢复的对象数量
        """
        root = await cls.get_root(session, user_id)
        if not root:
            raise ValueError("用户根目录不存在")

        restored_count = 0

        for obj in objects:
            if not obj.deleted_at:
                continue

            # 确定恢复目标目录
            target_parent_id = root.id
            if obj.deleted_original_parent_id:
                original_parent = await cls.get(
                    session,
                    (cls.id == obj.deleted_original_parent_id) & (cls.deleted_at == None)
                )
                if original_parent:
                    target_parent_id = original_parent.id

            # 解决同名冲突
            resolved_name = await cls._resolve_name_conflict(
                session, user_id, target_parent_id, obj.name
            )

            # 恢复对象
            obj.parent_id = target_parent_id
            obj.deleted_at = None
            obj.deleted_original_parent_id = None
            if resolved_name != obj.name:
                obj.name = resolved_name
            await obj.save(session, commit=False, refresh=False)
            restored_count += 1

        await session.commit()
        return restored_count

    # ==================== 删除（硬删除） ====================

    async def _collect_physical_file_refs(
        self,
        session: AsyncSession,
        user_id: UUID,
        *,
        include_deleted: bool = False,
    ) -> tuple[list[UUID], int]:
        """
        BFS 收集子树中所有 PhysicalFile ID 和总文件大小

        :param session: 数据库会话
        :param user_id: 用户UUID
        :param include_deleted: True 时包含已软删除的子对象（永久删除场景）
        :return: (physical_file_id 列表, 总文件大小)
        """
        physical_file_ids: list[UUID] = []
        total_file_size = 0

        if self.is_file and self.physical_file_id:
            physical_file_ids.append(self.physical_file_id)
            total_file_size += self.size

        if self.is_folder:
            get_children = File.get_all_children if include_deleted else File.get_children
            queue: list[UUID] = [self.id]
            while queue:
                parent_id = queue.pop(0)
                children = await get_children(session, user_id, parent_id)
                for child in children:
                    if child.is_file and child.physical_file_id:
                        physical_file_ids.append(child.physical_file_id)
                        total_file_size += child.size
                    elif child.is_folder:
                        queue.append(child.id)

        return physical_file_ids, total_file_size

    @classmethod
    async def delete(
        cls,
        session: AsyncSession,
        instances: 'File | list[File] | None' = None,
        *,
        condition: 'ColumnElement[bool] | bool | None' = None,
        commit: bool = True,
        cleanup_storage: bool = False,
        release_quota: bool = True,
    ) -> int:
        """
        删除对象，可选物理文件清理和配额释放

        ``cleanup_storage=True`` 时启用完整清理：

        1. BFS 收集子树所有 PhysicalFile 引用（删除前）
        2. 释放用户配额（同事务）
        3. 硬删除 DB 记录（CASCADE 处理子对象）
        4. PhysicalFile 引用计数清理 + 物理删除

        :param session: 数据库会话
        :param instances: 要删除的对象实例或列表
        :param condition: WHERE 条件（不支持与 cleanup_storage 同时使用）
        :param commit: 是否提交事务
        :param cleanup_storage: 是否清理物理文件
        :param release_quota: 是否释放用户配额
        :return: 删除的记录数
        """
        if cleanup_storage and condition is not None:
            raise ValueError("cleanup_storage 不支持与 condition 同时使用，请使用实例删除模式")

        # Phase 1: 收集物理文件引用和配额数据（DB 删除前）
        physical_file_ids: list[UUID] = []
        quota_map: dict[UUID, int] = {}

        if cleanup_storage and instances is not None:
            instance_list = instances if isinstance(instances, list) else [instances]
            for obj in instance_list:
                is_trash = obj.deleted_at is not None
                refs, file_size = await obj._collect_physical_file_refs(
                    session, obj.owner_id, include_deleted=is_trash,
                )
                physical_file_ids.extend(refs)
                if release_quota and file_size > 0:
                    quota_map[obj.owner_id] = quota_map.get(obj.owner_id, 0) + file_size

        # Phase 2: 释放配额（同事务）
        for owner_id, total_size in quota_map.items():
            user = await User.get(session, User.id == owner_id)
            if user:
                await user.adjust_storage(session, -total_size, commit=False)

        # Phase 3: 硬删除 DB 记录（CASCADE 自动清理子对象）
        deleted_count: int = await super().delete(
            session, instances, condition=condition, commit=commit,
        )

        # Phase 4: PhysicalFile 引用计数清理 + 物理删除
        for pf_id in physical_file_ids:
            pf = await PhysicalFile.get(session, PhysicalFile.id == pf_id)
            if pf:
                await pf.cleanup_if_unreferenced(session)

        return deleted_count

    # ==================== 复制 ====================

    async def copy_recursive(
        self,
        session: AsyncSession,
        dst_parent_id: UUID,
        user_id: UUID,
    ) -> tuple[int, list[UUID], int]:
        """
        递归复制对象

        对于文件：增加 PhysicalFile 引用计数，创建新的 Object 记录指向同一 PhysicalFile。
        对于目录：创建新目录，递归复制所有子对象。

        :param session: 数据库会话
        :param dst_parent_id: 目标父目录UUID
        :param user_id: 用户UUID
        :return: (复制数量, 新对象UUID列表, 复制的总文件大小)
        """
        copied_count = 0
        new_ids: list[UUID] = []
        total_copied_size = 0

        # 在 save() 之前保存需要的属性值，避免 commit 后对象过期导致懒加载失败
        src_is_folder = self.is_folder
        src_is_file = self.is_file
        src_id = self.id
        src_size = self.size
        src_physical_file_id = self.physical_file_id

        new_obj = File(
            name=self.name,
            type=self.type,
            size=self.size,
            password=self.password,
            parent_id=dst_parent_id,
            owner_id=user_id,
            policy_id=self.policy_id,
            physical_file_id=self.physical_file_id,
        )

        # 文件：增加物理文件引用计数
        if src_is_file and src_physical_file_id:
            physical_file = await PhysicalFile.get(session, PhysicalFile.id == src_physical_file_id)
            if physical_file:
                physical_file.increment_reference()
                physical_file = await physical_file.save(session)
            total_copied_size += src_size

        new_obj = await new_obj.save(session)
        copied_count += 1
        new_ids.append(new_obj.id)

        # 目录：递归复制子对象
        if src_is_folder:
            children = await File.get_children(session, user_id, src_id)
            for child in children:
                child_count, child_ids, child_size = await child.copy_recursive(
                    session, new_obj.id, user_id,
                )
                copied_count += child_count
                new_ids.extend(child_ids)
                total_copied_size += child_size

        return copied_count, new_ids, total_copied_size

    # ==================== 存储策略迁移 ====================

    async def migrate_to_policy(
        self,
        session: AsyncSession,
        dest_policy: "Policy",
    ) -> None:
        """
        将文件对象从当前存储策略迁移到目标策略

        :param session: 数据库会话
        :param dest_policy: 目标存储策略
        """
        from utils.storage.factory import create_storage_service
        from utils.storage import LocalStorageService

        if self.type != FileType.FILE:
            raise ValueError(f"只能迁移文件对象，当前类型: {self.type}")

        src_policy = await self.awaitable_attrs.policy
        old_physical: PhysicalFile | None = await self.awaitable_attrs.physical_file

        if not old_physical:
            l.warning(f"文件 {self.id} 没有关联物理文件，跳过迁移")
            return

        if src_policy.id == dest_policy.id:
            l.debug(f"文件 {self.id} 已在目标策略中，跳过")
            return

        # 1. 创建存储服务
        src_service = create_storage_service(src_policy)
        dest_service = create_storage_service(dest_policy)

        # 2. 从源存储读取文件
        if isinstance(src_service, LocalStorageService):
            data = await src_service.read_file(old_physical.storage_path)
        else:
            data = await src_service.download_file(old_physical.storage_path)

        # 3. 在目标存储生成新路径并写入
        _dir_path, _storage_name, new_storage_path = await dest_service.generate_file_path(
            user_id=self.owner_id,
            original_filename=self.name,
        )
        if isinstance(dest_service, LocalStorageService):
            await dest_service.write_file(new_storage_path, data)
        else:
            await dest_service.upload_file(new_storage_path, data)

        # 4. 创建新的 PhysicalFile
        new_physical = PhysicalFile(
            storage_path=new_storage_path,
            size=old_physical.size,
            checksum_md5=old_physical.checksum_md5,
            policy_id=dest_policy.id,
            reference_count=1,
        )
        new_physical = await new_physical.save(session)

        # 5. 更新 Object
        self.policy_id = dest_policy.id
        self.physical_file_id = new_physical.id
        await self.save(session)

        # 6. 旧 PhysicalFile 清理
        await old_physical.cleanup_if_unreferenced(session)

        l.info(f"文件迁移完成: {self.name} ({self.id}), {src_policy.name} → {dest_policy.name}")


# ==================== 上传会话模型 ====================

class UploadSessionBase(SQLModelBase):
    """上传会话基础字段"""

    file_name: Str255
    """原始文件名"""

    file_size: NonNegativeBigInt
    """文件总大小（字节）"""

    chunk_size: PositiveBigInt
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

    uploaded_size: NonNegativeBigInt = 0
    """已上传大小（字节）"""

    storage_path: str | None = Field(default=None, max_length=512)
    """文件存储路径"""

    s3_upload_id: Str256 | None = None
    """S3 Multipart Upload ID（仅 S3 策略使用）"""

    s3_part_etags: str | None = None
    """S3 已上传分片的 ETag 列表，JSON 格式 [[1,"etag1"],[2,"etag2"]]（仅 S3 策略使用）"""

    expires_at: datetime
    """会话过期时间"""

    # 外键
    owner_id: UUID = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    """上传者用户UUID"""

    parent_id: UUID = Field(foreign_key="file.id", index=True, ondelete="CASCADE")
    """目标父目录UUID"""

    policy_id: UUID = Field(foreign_key="policy.id", index=True, ondelete="RESTRICT")
    """存储策略UUID"""

    # 关系
    owner: "User" = Relationship()
    """上传者"""

    parent: "File" = Relationship(
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

    file_name: Str255
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

    file_id: UUID | None = None
    """完成后的文件对象UUID，未完成时为None"""


class CreateFileRequest(SQLModelBase):
    """创建空白文件请求 DTO"""

    name: Str255
    """文件名"""

    parent_id: UUID
    """父目录UUID"""

    policy_id: UUID | None = None
    """存储策略UUID，不指定则使用父目录的策略"""


class FileSwitchPolicyRequest(SQLModelBase):
    """切换对象存储策略请求"""

    policy_id: UUID
    """目标存储策略UUID"""

    is_migrate_existing: bool = False
    """（仅目录）是否迁移已有文件，默认 false 只影响新文件"""


# ==================== 对象操作相关 DTO ====================

class FileCopyRequest(SQLModelBase):
    """复制对象请求 DTO"""

    src_ids: list[UUID] = Field(min_length=1, max_length=100)
    """源对象UUID列表"""

    dst_id: UUID
    """目标文件夹UUID"""


class FileRenameRequest(SQLModelBase):
    """重命名对象请求 DTO"""

    id: UUID
    """对象UUID"""

    new_name: Str255
    """新名称"""


class FilePropertyResponse(SQLModelBase):
    """对象基本属性响应 DTO"""

    id: UUID
    """对象UUID"""

    name: Str255
    """对象名称"""

    type: FileType
    """对象类型"""

    size: int
    """文件大小（字节）"""

    mime_type: Str128 | None = None
    """MIME类型"""

    created_at: datetime
    """创建时间"""

    updated_at: datetime
    """修改时间"""

    parent_id: UUID | None
    """父目录UUID"""


class FilePropertyDetailResponse(FilePropertyResponse):
    """对象详细属性响应 DTO（继承基本属性）"""

    # 校验和（从 PhysicalFile 读取）
    checksum_md5: Str64 | None = None
    """MD5校验和"""

    checksum_sha256: Str64 | None = None
    """SHA256校验和"""

    # 分享统计
    share_count: int = 0
    """分享次数"""

    total_views: int = 0
    """总浏览次数"""

    total_downloads: int = 0
    """总下载次数"""

    # 存储信息
    policy_name: Str255 | None = None
    """存储策略名称"""

    reference_count: int = 1
    """物理文件引用计数（仅文件有效）"""

    # 元数据（KV 格式）
    metadatas: dict[str, str] = {}
    """所有元数据条目（键名 → 值）"""


# ==================== 管理员文件管理 DTO ====================

class AdminFileResponse(FileResponse):
    """管理员文件响应 DTO"""

    owner_id: UUID
    """所有者UUID"""

    owner_email: Str255
    """所有者邮箱"""

    policy_name: Str255
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
        obj: "File",
        owner: "User | None",
        policy: "Policy | None",
    ) -> "AdminFileResponse":
        """从 Object ORM 对象构建"""
        return cls(
            # ObjectBase 字段
            **FileBase.model_validate(obj, from_attributes=True).model_dump(),
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

    type: FileType
    """对象类型"""

    size: int
    """文件大小（字节）"""

    deleted_at: datetime
    """删除时间"""

    original_parent_id: UUID | None
    """原始父目录UUID"""


class TrashRestoreRequest(SQLModelBase):
    """恢复对象请求 DTO"""

    ids: list[UUID] = Field(min_length=1, max_length=100)
    """待恢复对象UUID列表"""


class TrashDeleteRequest(SQLModelBase):
    """永久删除对象请求 DTO"""

    ids: list[UUID] = Field(min_length=1, max_length=100)
    """待永久删除对象UUID列表"""
