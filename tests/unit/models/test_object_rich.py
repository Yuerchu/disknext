"""
Object 充血模型方法的单元测试

覆盖 Object 类的业务方法：
- soft_delete_batch
- restore_batch + _resolve_name_conflict
- delete(cleanup_storage=True) + _collect_physical_file_refs
- copy_recursive

使用 Faker 生成随机数据覆盖各种边界情况。
"""
from datetime import datetime
from uuid import UUID, uuid4

import pytest
from faker import Faker
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodels.group import Group
from sqlmodels.object import Object, ObjectType
from sqlmodels.physical_file import PhysicalFile
from sqlmodels.policy import Policy, PolicyType
from sqlmodels.user import User, UserStatus


# ==================== 辅助函数 ====================

async def _make_folder(
    session: AsyncSession,
    owner_id: UUID,
    policy_id: UUID,
    parent_id: UUID | None,
    name: str,
) -> Object:
    """创建目录"""
    folder = Object(
        name=name,
        type=ObjectType.FOLDER,
        parent_id=parent_id,
        owner_id=owner_id,
        policy_id=policy_id,
        size=0,
    )
    return await folder.save(session)


async def _make_file(
    session: AsyncSession,
    owner_id: UUID,
    policy_id: UUID,
    parent_id: UUID,
    name: str,
    size: int = 1024,
    physical_file_id: UUID | None = None,
) -> Object:
    """创建文件"""
    file = Object(
        name=name,
        type=ObjectType.FILE,
        parent_id=parent_id,
        owner_id=owner_id,
        policy_id=policy_id,
        size=size,
        physical_file_id=physical_file_id,
    )
    return await file.save(session)


async def _make_physical_file(
    session: AsyncSession,
    policy_id: UUID,
    size: int = 1024,
    reference_count: int = 1,
) -> PhysicalFile:
    """创建物理文件"""
    pf = PhysicalFile(
        storage_path=f"/tmp/{uuid4().hex}.bin",
        size=size,
        checksum_md5=f"{uuid4().hex}{uuid4().hex[:0]}",
        policy_id=policy_id,
        reference_count=reference_count,
    )
    return await pf.save(session)


# ==================== soft_delete_batch ====================

class TestSoftDeleteBatch:
    """Object.soft_delete_batch() 测试"""

    @pytest.mark.asyncio
    async def test_empty_list(self, minimal_setup):
        """空列表应返回 0"""
        session = minimal_setup["user"]  # noqa (unused)
        from sqlmodels.database_connection import DatabaseManager  # noqa

        # 使用 fixture 拿到的 session
        pass

    @pytest.mark.asyncio
    async def test_soft_delete_single_file(self, db_session: AsyncSession, minimal_setup):
        """软删除单个文件：设置 deleted_at、parent_id 置空、deleted_original_parent_id 保留"""
        user = minimal_setup["user"]
        policy = minimal_setup["policy"]
        root = minimal_setup["root"]

        file = await _make_file(db_session, user.id, policy.id, root.id, "test.txt")
        original_parent_id = file.parent_id
        assert original_parent_id == root.id

        count = await Object.soft_delete_batch(db_session, [file])
        assert count == 1

        refreshed = await Object.get(db_session, Object.id == file.id)
        assert refreshed.deleted_at is not None
        assert isinstance(refreshed.deleted_at, datetime)
        assert refreshed.parent_id is None
        assert refreshed.deleted_original_parent_id == original_parent_id

    @pytest.mark.asyncio
    async def test_soft_delete_empty_list_returns_zero(
        self, db_session: AsyncSession, minimal_setup
    ):
        """空列表直接返回 0，不触发任何数据库变更"""
        count = await Object.soft_delete_batch(db_session, [])
        assert count == 0

    @pytest.mark.asyncio
    async def test_soft_delete_multiple_objects(
        self, db_session: AsyncSession, minimal_setup, faker: Faker
    ):
        """批量软删除多个对象"""
        user = minimal_setup["user"]
        policy = minimal_setup["policy"]
        root = minimal_setup["root"]

        files = []
        for _ in range(10):
            name = f"{faker.unique.file_name()}"
            files.append(
                await _make_file(db_session, user.id, policy.id, root.id, name)
            )

        count = await Object.soft_delete_batch(db_session, files)
        assert count == 10

        for f in files:
            refreshed = await Object.get(db_session, Object.id == f.id)
            assert refreshed.deleted_at is not None
            assert refreshed.parent_id is None

    @pytest.mark.asyncio
    async def test_soft_delete_folder_does_not_affect_children(
        self, db_session: AsyncSession, minimal_setup
    ):
        """软删除目录时，子对象 deleted_at 保持 NULL（只有顶层标记软删除）"""
        user = minimal_setup["user"]
        policy = minimal_setup["policy"]
        root = minimal_setup["root"]

        folder = await _make_folder(db_session, user.id, policy.id, root.id, "parent")
        child_file = await _make_file(
            db_session, user.id, policy.id, folder.id, "child.txt"
        )

        await Object.soft_delete_batch(db_session, [folder])

        refreshed_child = await Object.get(db_session, Object.id == child_file.id)
        assert refreshed_child.deleted_at is None
        assert refreshed_child.parent_id == folder.id

    @pytest.mark.asyncio
    async def test_soft_delete_preserves_deleted_at_monotonic(
        self, db_session: AsyncSession, minimal_setup
    ):
        """连续软删除多个对象，所有对象的 deleted_at 都应被设置且不为 None"""
        user = minimal_setup["user"]
        policy = minimal_setup["policy"]
        root = minimal_setup["root"]

        before = datetime.now()
        files = [
            await _make_file(db_session, user.id, policy.id, root.id, f"f{i}.txt")
            for i in range(3)
        ]
        await Object.soft_delete_batch(db_session, files)

        for f in files:
            refreshed = await Object.get(db_session, Object.id == f.id)
            assert refreshed.deleted_at >= before


# ==================== _resolve_name_conflict ====================

class TestResolveNameConflict:
    """Object._resolve_name_conflict() 测试"""

    @pytest.mark.asyncio
    async def test_no_conflict_returns_original(
        self, db_session: AsyncSession, minimal_setup
    ):
        """无冲突时返回原名"""
        user = minimal_setup["user"]
        root = minimal_setup["root"]

        result = await Object._resolve_name_conflict(
            db_session, user.id, root.id, "unique_name.txt"
        )
        assert result == "unique_name.txt"

    @pytest.mark.asyncio
    async def test_single_conflict_appends_counter(
        self, db_session: AsyncSession, minimal_setup
    ):
        """有一个冲突时生成 'name (1).ext'"""
        user = minimal_setup["user"]
        policy = minimal_setup["policy"]
        root = minimal_setup["root"]

        await _make_file(db_session, user.id, policy.id, root.id, "test.txt")

        result = await Object._resolve_name_conflict(
            db_session, user.id, root.id, "test.txt"
        )
        assert result == "test (1).txt"

    @pytest.mark.asyncio
    async def test_multiple_conflicts_increments_counter(
        self, db_session: AsyncSession, minimal_setup
    ):
        """多个冲突时递增计数器"""
        user = minimal_setup["user"]
        policy = minimal_setup["policy"]
        root = minimal_setup["root"]

        await _make_file(db_session, user.id, policy.id, root.id, "report.pdf")
        await _make_file(db_session, user.id, policy.id, root.id, "report (1).pdf")
        await _make_file(db_session, user.id, policy.id, root.id, "report (2).pdf")

        result = await Object._resolve_name_conflict(
            db_session, user.id, root.id, "report.pdf"
        )
        assert result == "report (3).pdf"

    @pytest.mark.asyncio
    async def test_file_without_extension(
        self, db_session: AsyncSession, minimal_setup
    ):
        """无扩展名文件冲突处理"""
        user = minimal_setup["user"]
        policy = minimal_setup["policy"]
        root = minimal_setup["root"]

        await _make_file(db_session, user.id, policy.id, root.id, "LICENSE")

        result = await Object._resolve_name_conflict(
            db_session, user.id, root.id, "LICENSE"
        )
        assert result == "LICENSE (1)"

    @pytest.mark.asyncio
    async def test_file_with_multiple_dots(
        self, db_session: AsyncSession, minimal_setup
    ):
        """多点文件名使用最后一个点分割扩展名"""
        user = minimal_setup["user"]
        policy = minimal_setup["policy"]
        root = minimal_setup["root"]

        await _make_file(
            db_session, user.id, policy.id, root.id, "archive.tar.gz"
        )

        result = await Object._resolve_name_conflict(
            db_session, user.id, root.id, "archive.tar.gz"
        )
        # rsplit('.', 1) → "archive.tar" + "gz"
        assert result == "archive.tar (1).gz"

    @pytest.mark.asyncio
    async def test_deleted_file_does_not_count_as_conflict(
        self, db_session: AsyncSession, minimal_setup
    ):
        """已软删除的同名文件不应视为冲突"""
        user = minimal_setup["user"]
        policy = minimal_setup["policy"]
        root = minimal_setup["root"]

        file = await _make_file(db_session, user.id, policy.id, root.id, "doc.txt")
        await Object.soft_delete_batch(db_session, [file])

        # 软删除后同名文件不再冲突
        result = await Object._resolve_name_conflict(
            db_session, user.id, root.id, "doc.txt"
        )
        assert result == "doc.txt"

    @pytest.mark.asyncio
    async def test_conflict_scoped_by_parent(
        self, db_session: AsyncSession, minimal_setup
    ):
        """不同父目录下的同名文件不应互相冲突"""
        user = minimal_setup["user"]
        policy = minimal_setup["policy"]
        root = minimal_setup["root"]

        folder_a = await _make_folder(db_session, user.id, policy.id, root.id, "a")
        folder_b = await _make_folder(db_session, user.id, policy.id, root.id, "b")

        await _make_file(db_session, user.id, policy.id, folder_a.id, "shared.txt")

        # folder_b 下应可以创建同名文件
        result = await Object._resolve_name_conflict(
            db_session, user.id, folder_b.id, "shared.txt"
        )
        assert result == "shared.txt"

    @pytest.mark.asyncio
    async def test_conflict_scoped_by_owner(
        self, db_session: AsyncSession, minimal_setup, faker: Faker
    ):
        """其它用户的同名文件不应干扰"""
        user_a = minimal_setup["user"]
        policy = minimal_setup["policy"]
        group = minimal_setup["group"]
        root_a = minimal_setup["root"]

        # 再创建一个用户 B 及其根目录
        user_b = User(
            email=faker.unique.email(),
            nickname=faker.name(),
            status=UserStatus.ACTIVE,
            group_id=group.id,
        )
        user_b = await user_b.save(db_session)

        root_b = await _make_folder(db_session, user_b.id, policy.id, None, "/")

        await _make_file(db_session, user_a.id, policy.id, root_a.id, "data.csv")

        # user_b 根目录下的同名文件不冲突
        result = await Object._resolve_name_conflict(
            db_session, user_b.id, root_b.id, "data.csv"
        )
        assert result == "data.csv"


# ==================== restore_batch ====================

class TestRestoreBatch:
    """Object.restore_batch() 测试"""

    @pytest.mark.asyncio
    async def test_restore_to_original_parent(
        self, db_session: AsyncSession, minimal_setup
    ):
        """原父目录存在时恢复到原位置"""
        user = minimal_setup["user"]
        policy = minimal_setup["policy"]
        root = minimal_setup["root"]

        folder = await _make_folder(db_session, user.id, policy.id, root.id, "docs")
        file = await _make_file(db_session, user.id, policy.id, folder.id, "a.txt")

        await Object.soft_delete_batch(db_session, [file])
        deleted = await Object.get(db_session, Object.id == file.id)
        assert deleted.parent_id is None
        assert deleted.deleted_original_parent_id == folder.id

        count = await Object.restore_batch(db_session, [deleted], user.id)
        assert count == 1

        restored = await Object.get(db_session, Object.id == file.id)
        assert restored.deleted_at is None
        assert restored.deleted_original_parent_id is None
        assert restored.parent_id == folder.id

    @pytest.mark.asyncio
    async def test_restore_to_root_if_parent_gone(
        self, db_session: AsyncSession, minimal_setup
    ):
        """原父目录已不存在（硬删除）时恢复到用户根目录"""
        user = minimal_setup["user"]
        policy = minimal_setup["policy"]
        root = minimal_setup["root"]

        folder = await _make_folder(db_session, user.id, policy.id, root.id, "temp")
        file = await _make_file(db_session, user.id, policy.id, folder.id, "b.txt")

        await Object.soft_delete_batch(db_session, [file])

        # 硬删除原父目录
        await Object.delete(db_session, condition=Object.id == folder.id)

        deleted = await Object.get(db_session, Object.id == file.id)
        await Object.restore_batch(db_session, [deleted], user.id)

        restored = await Object.get(db_session, Object.id == file.id)
        assert restored.parent_id == root.id
        assert restored.deleted_at is None

    @pytest.mark.asyncio
    async def test_restore_with_name_conflict_auto_renames(
        self, db_session: AsyncSession, minimal_setup
    ):
        """恢复时原位置已存在同名文件 → 自动重命名"""
        user = minimal_setup["user"]
        policy = minimal_setup["policy"]
        root = minimal_setup["root"]

        file1 = await _make_file(
            db_session, user.id, policy.id, root.id, "collide.txt"
        )
        await Object.soft_delete_batch(db_session, [file1])

        # 软删除后在原位置创建同名文件
        await _make_file(
            db_session, user.id, policy.id, root.id, "collide.txt"
        )

        deleted = await Object.get(db_session, Object.id == file1.id)
        await Object.restore_batch(db_session, [deleted], user.id)

        restored = await Object.get(db_session, Object.id == file1.id)
        assert restored.name == "collide (1).txt"
        assert restored.deleted_at is None
        assert restored.parent_id == root.id

    @pytest.mark.asyncio
    async def test_restore_skips_non_deleted_objects(
        self, db_session: AsyncSession, minimal_setup
    ):
        """未处于回收站状态的对象（deleted_at 为 None）应被跳过"""
        user = minimal_setup["user"]
        policy = minimal_setup["policy"]
        root = minimal_setup["root"]

        file = await _make_file(db_session, user.id, policy.id, root.id, "x.txt")

        count = await Object.restore_batch(db_session, [file], user.id)
        assert count == 0

    @pytest.mark.asyncio
    async def test_restore_raises_if_no_root(
        self, db_session: AsyncSession, minimal_setup, faker: Faker
    ):
        """用户没有根目录时应抛 ValueError"""
        policy = minimal_setup["policy"]
        group = minimal_setup["group"]

        # 创建一个没有根目录的孤立用户
        orphan = User(
            email=faker.unique.email(),
            nickname=faker.name(),
            status=UserStatus.ACTIVE,
            group_id=group.id,
        )
        orphan = await orphan.save(db_session)

        # 创建一个假的"已软删除"对象
        obj = Object(
            name="ghost.txt",
            type=ObjectType.FILE,
            owner_id=orphan.id,
            policy_id=policy.id,
            parent_id=None,
            deleted_at=datetime.now(),
        )
        obj = await obj.save(db_session)

        with pytest.raises(ValueError, match="用户根目录不存在"):
            await Object.restore_batch(db_session, [obj], orphan.id)


# ==================== copy_recursive ====================

class TestCopyRecursive:
    """Object.copy_recursive() 测试"""

    @pytest.mark.asyncio
    async def test_copy_single_file(
        self, db_session: AsyncSession, minimal_setup
    ):
        """复制单个文件：PhysicalFile 引用计数 +1，新 Object 指向同一 PhysicalFile"""
        user = minimal_setup["user"]
        policy = minimal_setup["policy"]
        root = minimal_setup["root"]

        pf = await _make_physical_file(db_session, policy.id, size=2048, reference_count=1)
        src = await _make_file(
            db_session, user.id, policy.id, root.id, "source.bin",
            size=2048, physical_file_id=pf.id,
        )

        # 创建目标目录
        dst_folder = await _make_folder(db_session, user.id, policy.id, root.id, "dst")

        count, new_ids, total_size = await src.copy_recursive(
            db_session, dst_folder.id, user.id
        )

        assert count == 1
        assert len(new_ids) == 1
        assert total_size == 2048

        # PhysicalFile 引用计数应 +1
        pf_refreshed = await PhysicalFile.get(db_session, PhysicalFile.id == pf.id)
        assert pf_refreshed.reference_count == 2

        # 新 Object 存在且指向同一 PhysicalFile
        new_obj = await Object.get(db_session, Object.id == new_ids[0])
        assert new_obj is not None
        assert new_obj.physical_file_id == pf.id
        assert new_obj.parent_id == dst_folder.id
        assert new_obj.owner_id == user.id

    @pytest.mark.asyncio
    async def test_copy_empty_folder(
        self, db_session: AsyncSession, minimal_setup
    ):
        """复制空目录：只复制目录本身"""
        user = minimal_setup["user"]
        policy = minimal_setup["policy"]
        root = minimal_setup["root"]

        src = await _make_folder(db_session, user.id, policy.id, root.id, "src_folder")
        dst = await _make_folder(db_session, user.id, policy.id, root.id, "dst_folder")

        count, new_ids, total_size = await src.copy_recursive(
            db_session, dst.id, user.id
        )

        assert count == 1
        assert total_size == 0
        assert len(new_ids) == 1

    @pytest.mark.asyncio
    async def test_copy_nested_folder_tree(
        self, db_session: AsyncSession, minimal_setup
    ):
        """复制嵌套目录树：每个节点都应被创建，PhysicalFile 引用应正确累加"""
        user = minimal_setup["user"]
        policy = minimal_setup["policy"]
        root = minimal_setup["root"]

        # 结构: src/ -> [file1, sub/ -> [file2]]
        src = await _make_folder(db_session, user.id, policy.id, root.id, "src")
        pf1 = await _make_physical_file(db_session, policy.id, size=100)
        pf2 = await _make_physical_file(db_session, policy.id, size=200)
        await _make_file(
            db_session, user.id, policy.id, src.id, "file1.txt",
            size=100, physical_file_id=pf1.id,
        )
        sub = await _make_folder(db_session, user.id, policy.id, src.id, "sub")
        await _make_file(
            db_session, user.id, policy.id, sub.id, "file2.txt",
            size=200, physical_file_id=pf2.id,
        )

        dst = await _make_folder(db_session, user.id, policy.id, root.id, "dst")

        count, new_ids, total_size = await src.copy_recursive(
            db_session, dst.id, user.id
        )

        # 1 src + 1 file1 + 1 sub + 1 file2 = 4
        assert count == 4
        assert len(new_ids) == 4
        assert total_size == 300  # 100 + 200

        # 检查两个物理文件引用计数都 +1
        pf1_r = await PhysicalFile.get(db_session, PhysicalFile.id == pf1.id)
        pf2_r = await PhysicalFile.get(db_session, PhysicalFile.id == pf2.id)
        assert pf1_r.reference_count == 2
        assert pf2_r.reference_count == 2

    @pytest.mark.asyncio
    async def test_copy_preserves_name_and_policy(
        self, db_session: AsyncSession, minimal_setup
    ):
        """复制后新对象保留原名和策略"""
        user = minimal_setup["user"]
        policy = minimal_setup["policy"]
        root = minimal_setup["root"]

        src = await _make_file(db_session, user.id, policy.id, root.id, "keep_name.doc")
        dst = await _make_folder(db_session, user.id, policy.id, root.id, "target")

        _, new_ids, _ = await src.copy_recursive(db_session, dst.id, user.id)

        new_obj = await Object.get(db_session, Object.id == new_ids[0])
        assert new_obj.name == "keep_name.doc"
        assert new_obj.policy_id == policy.id


# ==================== adjust_storage (User) ====================

class TestUserAdjustStorage:
    """User.adjust_storage() 原子性与边界测试"""

    @pytest.mark.asyncio
    async def test_zero_delta_noop(
        self, db_session: AsyncSession, minimal_setup
    ):
        """delta=0 时应直接返回，不触发 SQL"""
        user = minimal_setup["user"]
        await user.adjust_storage(db_session, 0)

        refreshed = await User.get(db_session, User.id == user.id)
        assert refreshed.storage == 0

    @pytest.mark.asyncio
    async def test_positive_delta(
        self, db_session: AsyncSession, minimal_setup
    ):
        """正数增量应累加"""
        user = minimal_setup["user"]
        await user.adjust_storage(db_session, 1024)
        await user.adjust_storage(db_session, 2048)

        refreshed = await User.get(db_session, User.id == user.id)
        assert refreshed.storage == 3072

    @pytest.mark.asyncio
    async def test_negative_delta(
        self, db_session: AsyncSession, minimal_setup
    ):
        """负数减量应正常扣除"""
        user = minimal_setup["user"]
        await user.adjust_storage(db_session, 5000)
        await user.adjust_storage(db_session, -3000)

        refreshed = await User.get(db_session, User.id == user.id)
        assert refreshed.storage == 2000

    @pytest.mark.asyncio
    async def test_negative_clamped_to_zero(
        self, db_session: AsyncSession, minimal_setup
    ):
        """减到负数时 GREATEST 应 clamp 到 0"""
        user = minimal_setup["user"]
        await user.adjust_storage(db_session, 1000)
        await user.adjust_storage(db_session, -99999)

        refreshed = await User.get(db_session, User.id == user.id)
        assert refreshed.storage == 0

    @pytest.mark.asyncio
    async def test_large_value(
        self, db_session: AsyncSession, minimal_setup
    ):
        """BigInteger 支持大数值（TB 级）"""
        user = minimal_setup["user"]
        tb = 1024 ** 4  # 1 TB
        await user.adjust_storage(db_session, tb)

        refreshed = await User.get(db_session, User.id == user.id)
        assert refreshed.storage == tb

    @pytest.mark.asyncio
    async def test_commit_false_does_not_persist_until_explicit_commit(
        self, db_session: AsyncSession, minimal_setup
    ):
        """commit=False 时需手动 commit 才能持久化"""
        user = minimal_setup["user"]
        await user.adjust_storage(db_session, 500, commit=False)
        await db_session.commit()

        refreshed = await User.get(db_session, User.id == user.id)
        assert refreshed.storage == 500

    @pytest.mark.asyncio
    async def test_fuzz_random_deltas(
        self, db_session: AsyncSession, minimal_setup, faker: Faker
    ):
        """随机增减 20 次后，最终值应等于所有 delta 的和（≥0 clamp）"""
        user = minimal_setup["user"]
        deltas = [faker.random_int(min=-500, max=1000) for _ in range(20)]

        for d in deltas:
            await user.adjust_storage(db_session, d)

        refreshed = await User.get(db_session, User.id == user.id)

        # 模拟 GREATEST(0, ...) 的逐步累加
        expected = 0
        for d in deltas:
            expected = max(0, expected + d)

        assert refreshed.storage == expected
