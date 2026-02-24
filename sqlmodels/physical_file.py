"""
物理文件模型

表示磁盘上的实际文件。多个 Object 可以引用同一个 PhysicalFile，
实现文件共享而不复制物理文件。

引用计数逻辑：
- 每个引用此文件的 Object 都会增加引用计数
- 当 Object 被删除时，减少引用计数
- 只有当引用计数为 0 时，才物理删除文件
"""
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import BigInteger
from sqlmodel import Field, Relationship, Index

from sqlmodel_ext import SQLModelBase, UUIDTableBaseMixin

if TYPE_CHECKING:
    from .object import Object
    from .policy import Policy


class PhysicalFileBase(SQLModelBase):
    """物理文件基础模型"""

    storage_path: str = Field(max_length=512)
    """物理存储路径（相对于存储策略根目录）"""

    size: int = Field(default=0, sa_type=BigInteger)
    """文件大小（字节）"""

    checksum_md5: str | None = Field(default=None, max_length=32)
    """MD5校验和（用于文件去重和完整性校验）"""

    checksum_sha256: str | None = Field(default=None, max_length=64)
    """SHA256校验和"""


class PhysicalFile(PhysicalFileBase, UUIDTableBaseMixin):
    """
    物理文件模型

    表示磁盘上的实际文件。多个 Object 可以引用同一个 PhysicalFile，
    实现文件共享而不复制物理文件。
    """

    __table_args__ = (
        Index("ix_physical_file_policy_path", "policy_id", "storage_path"),
        Index("ix_physical_file_checksum", "checksum_md5"),
    )

    policy_id: UUID = Field(
        foreign_key="policy.id",
        index=True,
        ondelete="RESTRICT",
    )
    """存储策略UUID"""

    reference_count: int = Field(default=1, ge=0)
    """引用计数（有多少个 Object 引用此物理文件）"""

    # 关系
    policy: "Policy" = Relationship()
    """存储策略"""

    objects: list["Object"] = Relationship(back_populates="physical_file")
    """引用此物理文件的所有逻辑对象"""

    def increment_reference(self) -> int:
        """
        增加引用计数

        :return: 更新后的引用计数
        """
        self.reference_count += 1
        return self.reference_count

    def decrement_reference(self) -> int:
        """
        减少引用计数

        :return: 更新后的引用计数
        """
        if self.reference_count > 0:
            self.reference_count -= 1
        return self.reference_count

    @property
    def can_be_deleted(self) -> bool:
        """是否可以物理删除（引用计数为0）"""
        return self.reference_count == 0
