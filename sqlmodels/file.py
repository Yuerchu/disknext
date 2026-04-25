
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID
import re

from enum import StrEnum
from loguru import logger as l
from sqlmodel import Field, Relationship, CheckConstraint, Index, col, text
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel_ext import (
    SQLModelBase, 
    ListResponse,
    TableViewRequest,
    UUIDTableBaseMixin, 
    NonNegativeBigInt, 
    PositiveBigInt, 
    Str64, 
    Str128, 
    Str255, 
    Str256, 
    cond
)

from .policy import PolicyType
from .model_base import ResponseBase

if TYPE_CHECKING:
    from .user import User
    from .policy import Policy
    from .source_link import SourceLink
    from .share import Share
    from .physical_file import PhysicalFile
    from .uri import DiskNextURI
    from .file_metadata import EntryMetadata


class EntryType(StrEnum):
    """条目类型枚举"""
    FILE = "file"
    """文件"""
    FOLDER = "folder"
    """文件夹"""
    SYMLINK = "symlink"
    """软链接（删除不影响源，源被删则自动级联删除）"""


class FileCategory(StrEnum):
    """文件类型分类枚举，用于按类别筛选文件"""
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"


# ==================== Base 模型 ====================

class EntryBase(SQLModelBase):
    """对象基础字段，供数据库模型和 DTO 共享"""

    name: str = Field(min_length=1, max_length=255)
    """对象名称（文件名或目录名）"""

    type: EntryType
    """对象类型"""

    size: NonNegativeBigInt = 0
    """文件大小（字节）"""

    mime_type: str | None = Field(default=None, max_length=127)
    """MIME类型（仅文件有效）"""


# ==================== DTO 模型 ====================

class EntryFileFinalize(SQLModelBase):
    """文件上传完成后更新 Entry 的 DTO"""

    size: int
    """文件大小（字节）"""

    physical_file_id: UUID
    """关联的物理文件UUID"""


class EntryMoveUpdate(SQLModelBase):
    """移动/重命名 Entry 的 DTO"""

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


class EntryMoveRequest(SQLModelBase):
    """移动对象请求 DTO"""

    src_ids: list[UUID] = Field(min_length=1, max_length=100)
    """源对象UUID列表"""

    dst_id: UUID
    """目标文件夹UUID"""


class EntryDeleteRequest(SQLModelBase):
    """删除对象请求 DTO"""

    ids: list[UUID] = Field(min_length=1, max_length=100)
    """待删除对象UUID列表"""


class EntryResponse(EntryBase):
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

    objects: list[EntryResponse] = []
    """目录下的对象列表"""

    policy: PolicyResponse
    """存储策略"""


# ==================== 数据库模型 ====================

class Entry(EntryBase, UUIDTableBaseMixin):
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

    name: Str255
    """对象名称（文件名或目录名）"""

    type: EntryType
    """对象类型：file 或 folder"""

    password: Str255 | None = None
    """对象独立密码（仅当用户为对象单独设置密码时有效）"""

    # ==================== 文件专属字段 ====================

    size: NonNegativeBigInt = 0
    """文件大小（字节）"""

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
        foreign_key="entry.id",
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
        foreign_key="entry.id",
        ondelete="SET NULL",
    )
    """软删除前的原始父目录UUID（恢复时用于还原位置）"""

    # ==================== 关系 ====================

    owner: "User" = Relationship(
        back_populates="entries",
        sa_relationship_kwargs={"foreign_keys": "[Entry.owner_id]"}
    )
    """所有者"""

    banner: "User" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[Entry.banned_by]"}
    )
    """封禁操作者"""

    policy: "Policy" = Relationship(back_populates="entries")
    """存储策略"""

    # 自引用关系
    parent: "Entry" = Relationship(
        back_populates="children",
        sa_relationship_kwargs={
            "remote_side": "Entry.id",
            "foreign_keys": "[Entry.parent_id]",
        },
    )
    """父目录"""

    children: list["Entry"] = Relationship(
        back_populates="parent",
        cascade_delete=True,
        sa_relationship_kwargs={"foreign_keys": "[Entry.parent_id]"},
    )
    """子对象（文件和子目录）"""

    # 仅文件有效的关系
    metadata_entries: list["EntryMetadata"] = Relationship(back_populates="entry", cascade_delete=True)
    """元数据键值对列表"""

    source_links: list["SourceLink"] = Relationship(back_populates="entry", cascade_delete=True)
    """源链接列表（仅文件有效）"""

    shares: list["Share"] = Relationship(back_populates="entry", cascade_delete=True)
    """分享列表"""

    physical_file: "PhysicalFile" = Relationship(back_populates="entries")
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

    # ==================== 业务方法 ====================

    @classmethod
    async def get_root(cls, session, user_id: UUID) -> "Entry":
        """
        获取用户的根目录

        :param session: 数据库会话
        :param user_id: 用户UUID
        :return: 根目录对象，不存在则报错
        """
        return await cls.get(
            session,
            (cls.owner_id == user_id) & (cls.parent_id == None) & (cls.deleted_at == None),
            fetch_mode="one"
        )

    @classmethod
    async def get_by_path(
        cls,
        session,
        user_id: UUID,
        path: str,
    ) -> "Entry | None":
        """
        根据路径获取对象

        路径从用户根目录开始，不包含用户名前缀。
        如 "/" 表示根目录，"/docs/images" 表示根目录下的 docs/images。

        :param session: 数据库会话
        :param user_id: 用户UUID
        :param path: 路径，如 "/" 或 "/docs/images"
        :return: Entry 或 None
        """
        path = path.strip()
        if not path:
            raise ValueError("路径不能为空")

        # 移除开头的斜杠并分割路径
        if path.startswith("/"):
            path = path[1:]
        parts = [p for p in path.split("/") if p]

        # 空路径 -> 返回根目录
        if not parts:
            return await cls.get_root(session, user_id)

        # 动态自连接：N 段路径生成 1 条 SQL（e0=root, e1..eN=各段）
        # 对极深路径（> 20 层）回退到逐级查询
        if len(parts) > 20:
            root = await cls.get_root(session, user_id)
            if not root:
                return None
            current: Entry | None = root
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

        # 构建自连接 SQL
        joins = ["entry e0"]
        conditions = [
            "e0.owner_id = :user_id",
            "e0.parent_id IS NULL",
            "e0.deleted_at IS NULL",
        ]
        params: dict[str, str] = {"user_id": str(user_id)}

        for i, part in enumerate(parts):
            alias = f"e{i + 1}"
            prev = f"e{i}"
            joins.append(f"JOIN entry {alias} ON {alias}.parent_id = {prev}.id")
            conditions.append(f"{alias}.owner_id = :user_id")
            conditions.append(f"{alias}.name = :part_{i}")
            conditions.append(f"{alias}.deleted_at IS NULL")
            params[f"part_{i}"] = part

        last = f"e{len(parts)}"
        sql = f"SELECT {last}.id FROM {' '.join(joins)} WHERE {' AND '.join(conditions)}"

        result = await session.execute(text(sql), params)
        row = result.first()
        if not row:
            return None

        return await cls.get(session, cls.id == row[0])

    @classmethod
    async def get_children(cls, session, user_id: UUID, parent_id: UUID) -> list["Entry"]:
        """
        获取目录下的所有子对象（不包含已软删除的）

        :param session: 数据库会话
        :param user_id: 用户UUID
        :param parent_id: 父目录UUID
        :return: 子对象列表
        """
        return await cls.get(
            session,
            cond(cls.owner_id == user_id) & 
            cond(cls.parent_id == parent_id) & 
            cond(cls.deleted_at == None),
            fetch_mode="all"
        )

    @classmethod
    async def get_all_children(cls, session, user_id: UUID, parent_id: UUID) -> list["Entry"]:
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
    async def get_trash_items(cls, session, user_id: UUID) -> list["Entry"]:
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
    ) -> 'ListResponse[Entry]':
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
            (cls.type == EntryType.FILE) &
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
    ) -> "Entry":
        """
        将 URI 解析为 Entry 实例

        :param session: 数据库会话
        :param uri: DiskNextURI 实例
        :param requesting_user_id: 请求用户UUID
        :return: Entry 实例
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
            # [TODO] 但实际上单个用户也可授权自己的文件给其他用户访问
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

        使用递归 CTE 一次查询获取所有祖先节点名称。

        :param session: 数据库会话
        :return: 完整路径，如 "/docs/images/photo.jpg"
        """
        if self.parent_id is None:
            return "/"

        cte_sql = text('''
            WITH RECURSIVE ancestors AS (
                SELECT id, name, parent_id, 0 AS depth
                FROM entry WHERE id = :start_id

                UNION ALL

                SELECT e.id, e.name, e.parent_id, a.depth + 1
                FROM entry e
                JOIN ancestors a ON e.id = a.parent_id
                WHERE e.parent_id IS NOT NULL
            )
            SELECT name FROM ancestors ORDER BY depth DESC
        ''')
        result = await session.execute(cte_sql, {'start_id': str(self.id)})
        parts = [row[0] for row in result.all()]
        return "/" + "/".join(parts)

    # ==================== 软删除 ====================

    @classmethod
    async def soft_delete_batch(
        cls,
        session: AsyncSession,
        objects: list["Entry"],
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

        # 单次 LIKE 查询找出所有已存在的编号变体
        like_pattern = f"{base} (%){ext}"
        existing_variants = await cls.get(
            session,
            (cls.owner_id == user_id) &
            (cls.parent_id == parent_id) &
            (cls.name.like(like_pattern)) &
            (cls.deleted_at == None),
            fetch_mode="all",
        )

        # 正则提取已用编号
        used_numbers: set[int] = set()
        pattern_re = re.compile(rf'^{re.escape(base)} \((\d+)\){re.escape(ext)}$')
        for e in existing_variants:
            m = pattern_re.match(e.name)
            if m:
                used_numbers.add(int(m.group(1)))

        counter = 1
        while counter in used_numbers:
            counter += 1
        return f"{base} ({counter}){ext}"

    @classmethod
    async def restore_batch(
        cls,
        session: AsyncSession,
        objects: list["Entry"],
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

    # ==================== 永久删除 ====================

    async def _collect_file_entries_all(
        self,
        session: AsyncSession,
        user_id: UUID,
    ) -> tuple[list[tuple[UUID, str, UUID]], int, int]:
        """
        BFS 收集子树中所有文件的物理文件信息（包含已删除和未删除的子对象）

        :param session: 数据库会话
        :param user_id: 用户UUID
        :return: (文件条目列表[(obj_id, name, physical_file_id)], 总对象数, 总文件大小)
        """
        file_entries: list[tuple[UUID, str, UUID]] = []
        total_count = 1
        total_file_size = 0

        # 根对象本身是文件
        if self.type == EntryType.FILE and self.physical_file_id:
            file_entries.append((self.id, self.name, self.physical_file_id))
            total_file_size += self.size

        # BFS 遍历子目录
        if self.type == EntryType.FOLDER:
            queue: list[UUID] = [self.id]
            while queue:
                parent_id = queue.pop(0)
                children = await Entry.get_all_children(session, user_id, parent_id)
                for child in children:
                    total_count += 1
                    if child.type == EntryType.FILE and child.physical_file_id:
                        file_entries.append((child.id, child.name, child.physical_file_id))
                        total_file_size += child.size
                    elif child.type == EntryType.FOLDER:
                        queue.append(child.id)

        return file_entries, total_count, total_file_size

    @classmethod
    async def permanently_delete_batch(
        cls,
        session: AsyncSession,
        objects: list["Entry"],
        user_id: UUID,
    ) -> int:
        """
        永久删除回收站中的对象

        验证对象在回收站中（deleted_at IS NOT NULL），
        BFS 收集所有子文件的 PhysicalFile 信息，
        处理引用计数，引用为 0 时物理删除文件，
        最后硬删除根 Object（CASCADE 自动清理子对象）。

        :param session: 数据库会话
        :param objects: 待永久删除的对象列表
        :param user_id: 用户UUID
        :return: 永久删除的对象数量
        """
        from .physical_file import PhysicalFile
        from .policy import Policy
        from .user import User
        from utils.storage.factory import create_storage_driver

        total_deleted = 0

        for obj in objects:
            if not obj.deleted_at:
                l.warning(f"对象 {obj.id} 不在回收站中，跳过永久删除")
                continue

            root_id = obj.id
            file_entries, obj_count, total_file_size = await obj._collect_file_entries_all(
                session, user_id
            )

            # 批量获取所有 PhysicalFile（单次 SQL）
            pf_ids = list({pf_id for _, _, pf_id in file_entries})
            pf_map: dict[UUID, PhysicalFile] = {}
            if pf_ids:
                pf_list = await PhysicalFile.get(
                    session, col(PhysicalFile.id).in_(pf_ids), fetch_mode="all",
                )
                pf_map = {pf.id: pf for pf in pf_list}

            # 处理引用计数，收集可删除的 PhysicalFile
            deletable_pfs: list[PhysicalFile] = []
            for obj_id, obj_name, physical_file_id in file_entries:
                physical_file = pf_map.get(physical_file_id)
                if not physical_file:
                    continue

                physical_file.decrement_reference()

                if physical_file.can_be_deleted:
                    deletable_pfs.append(physical_file)
                else:
                    physical_file = await physical_file.save(session, commit=False)
                    l.debug(f"物理文件仍有 {physical_file.reference_count} 个引用: {physical_file.storage_path}")

            # 批量获取可删除文件的 Policy（单次 SQL）
            policy_ids = list({pf.policy_id for pf in deletable_pfs})
            policy_map: dict[UUID, Policy] = {}
            if policy_ids:
                policy_list = await Policy.get(
                    session, col(Policy.id).in_(policy_ids), fetch_mode="all",
                )
                policy_map = {p.id: p for p in policy_list}

            # 物理删除文件
            for physical_file in deletable_pfs:
                policy = policy_map.get(physical_file.policy_id)
                if policy:
                    try:
                        driver = create_storage_driver(policy)
                        await driver.delete(physical_file.storage_path)
                        l.debug(f"物理文件已删除: {physical_file.storage_path}")
                    except Exception as e:
                        l.warning(f"物理删除文件失败: {physical_file.storage_path}, 错误: {e}")

                await PhysicalFile.delete(session, physical_file, commit=False)
                l.debug(f"物理文件记录已删除: {physical_file.storage_path}")

            # 更新用户存储配额
            if total_file_size > 0:
                user = await User.get(session, User.id == user_id)
                if user:
                    await user.adjust_storage(session, -total_file_size, commit=False)

            # 硬删除根对象，CASCADE 自动删除所有子对象
            await cls.delete(session, condition=cls.id == root_id, commit=False)

            total_deleted += obj_count

        # 统一提交所有变更
        await session.commit()
        return total_deleted

    # ==================== 递归删除（硬删除） ====================

    async def delete_recursive(
        self,
        session: AsyncSession,
        user_id: UUID,
    ) -> int:
        """
        删除对象及其所有子对象（硬删除）

        两阶段策略：
        1. BFS 只读收集所有文件的 PhysicalFile 信息
        2. 批量处理引用计数，最后删除根对象触发 CASCADE

        :param session: 数据库会话
        :param user_id: 用户UUID
        :return: 删除的对象数量
        """
        from .physical_file import PhysicalFile
        from .policy import Policy
        from .user import User
        from utils.storage.factory import create_storage_driver

        # 阶段一：只读收集
        root_id = self.id
        file_entries: list[tuple[UUID, str, UUID]] = []
        total_count = 1
        total_file_size = 0

        if self.type == EntryType.FILE and self.physical_file_id:
            file_entries.append((self.id, self.name, self.physical_file_id))
            total_file_size += self.size

        if self.type == EntryType.FOLDER:
            queue: list[UUID] = [self.id]
            while queue:
                parent_id = queue.pop(0)
                children = await Entry.get_children(session, user_id, parent_id)
                for child in children:
                    total_count += 1
                    if child.type == EntryType.FILE and child.physical_file_id:
                        file_entries.append((child.id, child.name, child.physical_file_id))
                        total_file_size += child.size
                    elif child.type == EntryType.FOLDER:
                        queue.append(child.id)

        # 阶段二：批量获取所有 PhysicalFile（单次 SQL）
        pf_ids = list({pf_id for _, _, pf_id in file_entries})
        pf_map: dict[UUID, PhysicalFile] = {}
        if pf_ids:
            pf_list = await PhysicalFile.get(
                session, col(PhysicalFile.id).in_(pf_ids), fetch_mode="all",
            )
            pf_map = {pf.id: pf for pf in pf_list}

        # 处理引用计数，收集可删除的 PhysicalFile
        deletable_pfs: list[PhysicalFile] = []
        for _, _, physical_file_id in file_entries:
            physical_file = pf_map.get(physical_file_id)
            if not physical_file:
                continue

            physical_file.decrement_reference()

            if physical_file.can_be_deleted:
                deletable_pfs.append(physical_file)
            else:
                physical_file = await physical_file.save(session, commit=False)
                l.debug(f"物理文件仍有 {physical_file.reference_count} 个引用: {physical_file.storage_path}")

        # 批量获取可删除文件的 Policy（单次 SQL）
        policy_ids = list({pf.policy_id for pf in deletable_pfs})
        policy_map: dict[UUID, 'Policy'] = {}
        if policy_ids:
            policy_list = await Policy.get(
                session, col(Policy.id).in_(policy_ids), fetch_mode="all",
            )
            policy_map = {p.id: p for p in policy_list}

        # 物理删除文件
        for physical_file in deletable_pfs:
            policy = policy_map.get(physical_file.policy_id)
            if policy:
                try:
                    driver = create_storage_driver(policy)
                    await driver.delete(physical_file.storage_path)
                    l.debug(f"物理文件已删除: {physical_file.storage_path}")
                except Exception as e:
                    l.warning(f"物理删除文件失败: {physical_file.storage_path}, 错误: {e}")

            await PhysicalFile.delete(session, physical_file, commit=False)
            l.debug(f"物理文件记录已删除: {physical_file.storage_path}")

        # 阶段三：更新用户存储配额
        if total_file_size > 0:
            user = await User.get(session, User.id == user_id)
            if user:
                await user.adjust_storage(session, -total_file_size, commit=False)

        # 阶段四：删除根对象，CASCADE 自动删除所有子对象
        await Entry.delete(session, condition=Entry.id == root_id)

        return total_count

    # ==================== 复制 ====================

    async def _collect_physical_file_ids(
        self,
        session: AsyncSession,
        user_id: UUID,
    ) -> set[UUID]:
        """
        BFS 收集子树中所有文件的 physical_file_id

        :param session: 数据库会话
        :param user_id: 用户UUID
        :return: physical_file_id 集合
        """
        pf_ids: set[UUID] = set()

        if self.type == EntryType.FILE and self.physical_file_id:
            pf_ids.add(self.physical_file_id)

        if self.type == EntryType.FOLDER:
            queue: list[UUID] = [self.id]
            while queue:
                parent_id = queue.pop(0)
                children = await Entry.get_children(session, user_id, parent_id)
                for child in children:
                    if child.type == EntryType.FILE and child.physical_file_id:
                        pf_ids.add(child.physical_file_id)
                    elif child.type == EntryType.FOLDER:
                        queue.append(child.id)

        return pf_ids

    async def copy_recursive(
        self,
        session: AsyncSession,
        dst_parent_id: UUID,
        user_id: UUID,
    ) -> tuple[int, list[UUID], int]:
        """
        递归复制对象

        对于文件：增加 PhysicalFile 引用计数，创建新的 Entry 记录指向同一 PhysicalFile。
        对于目录：创建新目录，递归复制所有子对象。

        :param session: 数据库会话
        :param dst_parent_id: 目标父目录UUID
        :param user_id: 用户UUID
        :return: (复制数量, 新对象UUID列表, 复制的总文件大小)
        """
        from .physical_file import PhysicalFile

        # 批量预取所有 PhysicalFile（单次 SQL）
        pf_ids = await self._collect_physical_file_ids(session, user_id)
        pf_map: dict[UUID, PhysicalFile] = {}
        if pf_ids:
            pf_list = await PhysicalFile.get(
                session, col(PhysicalFile.id).in_(list(pf_ids)), fetch_mode="all",
            )
            pf_map = {pf.id: pf for pf in pf_list}

        return await self._copy_recursive_impl(session, dst_parent_id, user_id, pf_map)

    async def _copy_recursive_impl(
        self,
        session: AsyncSession,
        dst_parent_id: UUID,
        user_id: UUID,
        pf_map: 'dict[UUID, PhysicalFile]',
    ) -> tuple[int, list[UUID], int]:
        """递归复制内部实现"""
        copied_count = 0
        new_ids: list[UUID] = []
        total_copied_size = 0

        # 创建新的 Entry 记录
        new_obj = Entry(
            name=self.name,
            type=self.type,
            size=self.size,
            password=self.password,
            parent_id=dst_parent_id,
            owner_id=user_id,
            policy_id=self.policy_id,
            physical_file_id=self.physical_file_id,
        )

        # 如果是文件，增加物理文件引用计数
        if self.type == EntryType.FILE and self.physical_file_id:
            physical_file = pf_map.get(self.physical_file_id)
            if physical_file:
                physical_file.increment_reference()
                physical_file = await physical_file.save(session)
            total_copied_size += self.size

        new_obj = await new_obj.save(session)
        copied_count += 1
        new_ids.append(new_obj.id)

        # 如果是目录，递归复制子对象
        if self.type == EntryType.FOLDER:
            children = await Entry.get_children(session, user_id, self.id)
            for child in children:
                child_count, child_ids, child_size = await child._copy_recursive_impl(
                    session, new_obj.id, user_id, pf_map
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
        from .physical_file import PhysicalFile
        from .policy import Policy
        from utils.storage.factory import create_storage_driver

        if self.type != EntryType.FILE:
            raise ValueError(f"只能迁移文件对象，当前类型: {self.type}")

        src_policy: Policy = await self.awaitable_attrs.policy
        old_physical: PhysicalFile | None = await self.awaitable_attrs.physical_file

        if not old_physical:
            l.warning(f"文件 {self.id} 没有关联物理文件，跳过迁移")
            return

        if src_policy.id == dest_policy.id:
            l.debug(f"文件 {self.id} 已在目标策略中，跳过")
            return

        # 1. 创建存储驱动
        src_driver = create_storage_driver(src_policy)
        dest_driver = create_storage_driver(dest_policy)

        # 2. 从源存储读取文件
        data = await src_driver.read(old_physical.storage_path)

        # 3. 在目标存储生成新路径并写入
        _dir_path, _storage_name, new_storage_path = await dest_driver.generate_path(
            user_id=self.owner_id,
            original_filename=self.name,
        )
        await dest_driver.write(new_storage_path, data)

        # 4. 创建新的 PhysicalFile
        new_physical = PhysicalFile(
            storage_path=new_storage_path,
            size=old_physical.size,
            checksum_md5=old_physical.checksum_md5,
            policy_id=dest_policy.id,
            reference_count=1,
        )
        new_physical = await new_physical.save(session)

        # 5. 更新 Entry
        self.policy_id = dest_policy.id
        self.physical_file_id = new_physical.id
        self = await self.save(session)

        # 6. 旧 PhysicalFile 引用计数 -1
        old_physical.decrement_reference()
        if old_physical.can_be_deleted:
            try:
                await src_driver.delete(old_physical.storage_path)
            except Exception as e:
                l.warning(f"删除源文件失败（不影响迁移结果）: {old_physical.storage_path}: {e}")
            await PhysicalFile.delete(session, old_physical)
        else:
            old_physical = await old_physical.save(session)

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

    parent_id: UUID = Field(foreign_key="entry.id", index=True, ondelete="CASCADE")
    """目标父目录UUID"""

    policy_id: UUID = Field(foreign_key="policy.id", index=True, ondelete="RESTRICT")
    """存储策略UUID"""

    # 关系
    owner: "User" = Relationship()
    """上传者"""

    parent: "Entry" = Relationship(
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

    object_id: UUID | None = None
    """完成后的文件对象UUID，未完成时为None"""


class CreateFileRequest(SQLModelBase):
    """创建空白文件请求 DTO"""

    name: Str255
    """文件名"""

    parent_id: UUID
    """父目录UUID"""

    policy_id: UUID | None = None
    """存储策略UUID，不指定则使用父目录的策略"""


class EntrySwitchPolicyRequest(SQLModelBase):
    """切换对象存储策略请求"""

    policy_id: UUID
    """目标存储策略UUID"""

    is_migrate_existing: bool = False
    """（仅目录）是否迁移已有文件，默认 false 只影响新文件"""


# ==================== 对象操作相关 DTO ====================

class EntryCopyRequest(SQLModelBase):
    """复制对象请求 DTO"""

    src_ids: list[UUID] = Field(min_length=1, max_length=100)
    """源对象UUID列表"""

    dst_id: UUID
    """目标文件夹UUID"""


class EntryUpdateRequest(SQLModelBase):
    """对象更新请求 DTO（用于重命名等部分更新）"""

    name: Str255 | None = None
    """新名称（传入则更新）"""


class EntryPropertyResponse(SQLModelBase):
    """对象基本属性响应 DTO"""

    id: UUID
    """对象UUID"""

    name: Str255
    """对象名称"""

    type: EntryType
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


class EntryPropertyDetailResponse(EntryPropertyResponse):
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

class AdminFileResponse(EntryResponse):
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

    type: EntryType
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

    ids: list[UUID] = []
    """待永久删除对象UUID列表（is_empty_all=False 时必填）"""

    is_empty_all: bool = False
    """是否清空整个回收站（为 True 时忽略 ids）"""


class TextContentResponse(ResponseBase):
    """文本文件内容响应"""

    content: str
    """文件文本内容（UTF-8）"""

    hash: str
    """SHA-256 hex"""

    size: int
    """文件字节大小"""


class PatchContentRequest(SQLModelBase):
    """增量保存请求"""

    patch: str
    """unified diff 文本"""

    base_hash: str
    """原始内容的 SHA-256 hex（64字符）"""


class PatchContentResponse(ResponseBase):
    """增量保存响应"""

    new_hash: str
    """新内容的 SHA-256 hex"""

    new_size: int
    """新文件字节大小"""


class SourceLinkResponse(ResponseBase):
    """外链响应"""

    url: str
    """外链地址（永久有效，/source/ 端点自动 302 适配存储策略）"""

    downloads: int
    """历史下载次数"""