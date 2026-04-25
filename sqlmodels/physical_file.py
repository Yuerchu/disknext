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

from loguru import logger as l
from sqlmodel import Field, Relationship, Index
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodel_ext import SQLModelBase, UUIDTableBaseMixin, NonNegativeBigInt, Str32, Str64

from .policy import Policy
from utils.storage.factory import create_storage_service

if TYPE_CHECKING:
    from .file import Entry


class PhysicalFileBase(SQLModelBase):
    """物理文件基础模型"""

    storage_path: str = Field(max_length=512)
    """物理存储路径（相对于存储策略根目录）"""

    size: NonNegativeBigInt = 0
    """文件大小（字节）"""

    checksum_md5: Str32 | None = None
    """MD5校验和（用于文件去重和完整性校验）"""

    checksum_sha256: Str64 | None = None
    """SHA256校验和"""


class PhysicalFile(PhysicalFileBase, UUIDTableBaseMixin):
    """
    物理文件模型

    表示磁盘上的实际文件。多个 Object 可以引用同一个 PhysicalFile，
    实现文件共享而不复制物理文件。
    """

    __table_args__ = (
        Index("ix_physical_file_policy_path", "policy_id", "storage_path"),
    )

    checksum_md5: Str32 | None = Field(default=None, index=True)
    """MD5校验和（用于文件去重和完整性校验）"""

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

    entries: list["Entry"] = Relationship(back_populates="physical_file")
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

    async def cleanup_if_unreferenced(self, session: AsyncSession, *, commit: bool = False) -> bool:
        """
        减少引用计数，归零时删除物理文件和 DB 记录。

        物理删除失败仅记录警告（孤立文件可后续清理），不阻塞 DB 删除。

        :param session: 数据库会话
        :param commit: 是否提交事务
        :return: 是否已物理删除
        """
        self.decrement_reference()
        if not self.can_be_deleted:
            refreshed = await self.save(session, commit=commit)
            l.debug(f"物理文件仍有 {refreshed.reference_count} 个引用: {refreshed.storage_path}")
            return False

        # 物理删除
        policy = await Policy.get(session, Policy.id == self.policy_id)
        if policy:
            try:
                storage = create_storage_service(policy)
                await storage.delete_file(self.storage_path)
                l.debug(f"物理文件已删除: {self.storage_path}")
            except Exception as e:
                l.warning(f"物理删除失败（孤立文件可后续清理）: {self.storage_path}, error={e}")

        await PhysicalFile.delete(session, self, commit=commit)
        l.debug(f"物理文件记录已删除: {self.storage_path}")
        return True
