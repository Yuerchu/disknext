
from datetime import datetime
from typing import TYPE_CHECKING, Literal, Optional

from enum import StrEnum
from sqlmodel import Field, Relationship, UniqueConstraint, CheckConstraint, Index

from .base import TableBase, SQLModelBase

if TYPE_CHECKING:
    from .user import User
    from .policy import Policy
    from .source_link import SourceLink
    from .share import Share


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
    """对象类型：file 或 folder"""

    size: int = 0
    """文件大小（字节），目录为 0"""


# ==================== DTO 模型 ====================

class DirectoryCreateRequest(SQLModelBase):
    """创建目录请求 DTO"""

    path: str
    """目录路径，如 /docs/images"""

    policy_id: int | None = None
    """存储策略ID，不指定则继承父目录"""


class ObjectResponse(ObjectBase):
    """对象响应 DTO"""

    id: str
    """对象ID"""

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

    id: str
    """策略ID"""

    name: str
    """策略名称"""

    type: Literal["local", "qiniu", "tencent", "aliyun", "onedrive", "google_drive", "dropbox", "webdav", "remote"]
    """存储类型"""

    max_size: int = 0
    """单文件最大限制，单位字节，0表示不限制"""

    file_type: list[str] | None = None
    """允许的文件类型列表，None 表示不限制"""


class DirectoryResponse(SQLModelBase):
    """目录响应 DTO"""

    parent: str | None = None
    """父目录ID，根目录为None"""

    objects: list[ObjectResponse] = []
    """目录下的对象列表"""

    policy: PolicyResponse
    """存储策略"""


# ==================== 数据库模型 ====================

class Object(ObjectBase, TableBase, table=True):
    """
    统一对象模型

    合并了原有的 File 和 Folder 模型，通过 type 字段区分文件和目录。

    根目录规则：
    - 每个用户有一个显式根目录对象（name="my", parent_id=NULL）
    - 用户创建的文件/文件夹的 parent_id 指向根目录或其他文件夹的 id
    - 根目录的 policy_id 指定用户默认存储策略
    """

    __table_args__ = (
        # 同一父目录下名称唯一（包括 parent_id 为 NULL 的情况）
        UniqueConstraint("owner_id", "parent_id", "name", name="uq_object_parent_name"),
        # 名称不能包含斜杠
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

    source_name: str | None = None
    """源文件名（仅文件有效）"""

    size: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    """文件大小（字节），目录为 0"""

    upload_session_id: str | None = Field(default=None, max_length=255, unique=True, index=True)
    """分块上传会话ID（仅文件有效）"""

    # [TODO] 拆分
    file_metadata: str | None = None
    """文件元数据 (JSON格式)，仅文件有效"""

    # ==================== 外键 ====================

    parent_id: int | None = Field(default=None, foreign_key="object.id", index=True)
    """父目录ID，NULL 表示这是用户的根目录"""

    owner_id: int = Field(foreign_key="user.id", index=True)
    """所有者用户ID"""

    policy_id: int = Field(foreign_key="policy.id", index=True)
    """存储策略ID（文件直接使用，目录作为子文件的默认策略）"""

    # ==================== 关系 ====================

    owner: "User" = Relationship(back_populates="objects")
    """所有者"""

    policy: "Policy" = Relationship(back_populates="objects")
    """存储策略"""

    # 自引用关系
    parent: Optional["Object"] = Relationship(
        back_populates="children",
        sa_relationship_kwargs={"remote_side": "Object.id"},
    )
    """父目录"""

    children: list["Object"] = Relationship(back_populates="parent")
    """子对象（文件和子目录）"""

    # 仅文件有效的关系
    source_links: list["SourceLink"] = Relationship(back_populates="object")
    """源链接列表（仅文件有效）"""

    shares: list["Share"] = Relationship(back_populates="object")
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
    async def get_root(cls, session, user_id: int) -> "Object | None":
        """
        获取用户的根目录

        :param session: 数据库会话
        :param user_id: 用户ID
        :return: 根目录对象，不存在则返回 None
        """
        return await cls.get(
            session,
            (cls.owner_id == user_id) & (cls.parent_id == None)
        )

    @classmethod
    async def get_by_path(cls, session, user_id: int, path: str) -> "Object | None":
        """
        根据路径获取对象

        :param session: 数据库会话
        :param user_id: 用户ID
        :param path: 路径，如 "/" 或 "/docs/images"
        :return: Object 或 None
        """
        path = path.strip()
        if not path:
            raise ValueError("路径不能为空")

        if path in ["/my"]:
            return await cls.get_root(session, user_id)

        # 移除开头的斜杠并分割路径
        if path.startswith("/"):
            path = path[1:]
        parts = [p for p in path.split("/") if p]

        if not parts:
            return await cls.get_root(session, user_id)

        # 从根目录开始遍历
        current = await cls.get_root(session, user_id)

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
    async def get_children(cls, session, user_id: int, parent_id: int) -> list["Object"]:
        """
        获取目录下的所有子对象

        :param session: 数据库会话
        :param user_id: 用户ID
        :param parent_id: 父目录ID
        :return: 子对象列表
        """
        return await cls.get(
            session,
            (cls.owner_id == user_id) & (cls.parent_id == parent_id),
            fetch_mode="all"
        )
