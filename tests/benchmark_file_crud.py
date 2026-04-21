"""
文件 CRUD 性能基准测试

测试 get_by_path（动态 JOIN 链）、_collect_physical_file_refs（递归 CTE）、
is_ancestor_of（递归 CTE）的实际性能。

用法：
    .venv/Scripts/python.exe tests/benchmark_file_crud.py
"""
import asyncio
import os
import sys
import time
from uuid import UUID

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker

from sqlmodels.file import Entry, EntryType
from sqlmodels.physical_file import PhysicalFile
from sqlmodels.policy import Policy


async def setup_db() -> sessionmaker:
    """创建引擎和表"""
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        print("ERROR: TEST_DATABASE_URL 未设置")
        sys.exit(1)

    db_name = url.rsplit("/", 1)[-1]
    if "test" not in db_name and "dev" not in db_name:
        print(f"ERROR: 数据库名 '{db_name}' 必须包含 'test' 或 'dev'")
        sys.exit(1)

    engine = create_async_engine(url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)

    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def create_test_data(session: AsyncSession, depth: int, breadth: int) -> tuple[UUID, UUID, UUID]:
    """
    创建测试目录树

    :param depth: 目录深度
    :param breadth: 每层目录下的文件数
    :return: (user_id_placeholder, root_id, deepest_folder_id)
    """
    # 创建策略
    policy = Policy(
        name="bench_policy",
        type="local",
        server="/tmp/bench",
    )
    session.add(policy)
    await session.flush()

    # 用一个假 user_id（测试中不需要真 User 记录，因为没有 FK 约束 enforce）
    # 实际上有 FK 约束，需要创建真 User
    from sqlmodels.user import User
    from sqlmodels.group import Group

    group = Group(name="bench_group", max_storage=0)
    session.add(group)
    await session.flush()

    user = User(
        email="bench@test.local",
        nickname="bench",
        group_id=group.id,
    )
    session.add(user)
    await session.flush()
    user_id = user.id

    # 创建根目录
    root = Entry(
        name="/",
        type=EntryType.FOLDER,
        owner_id=user_id,
        parent_id=None,
        policy_id=policy.id,
    )
    session.add(root)
    await session.flush()

    # 创建深层目录链: /level_0/level_1/.../level_{depth-1}
    current_parent_id = root.id
    folder_ids: list[UUID] = [root.id]

    for i in range(depth):
        folder = Entry(
            name=f"level_{i}",
            type=EntryType.FOLDER,
            owner_id=user_id,
            parent_id=current_parent_id,
            policy_id=policy.id,
        )
        session.add(folder)
        await session.flush()
        current_parent_id = folder.id
        folder_ids.append(folder.id)

    deepest_folder_id = current_parent_id

    # 在每个目录下创建文件
    file_count = 0
    for folder_id in folder_ids:
        for j in range(breadth):
            # 创建 PhysicalFile
            pf = PhysicalFile(
                storage_path=f"/tmp/bench/{folder_id}/{j}.dat",
                size=1024 * (j + 1),
                policy_id=policy.id,
                reference_count=1,
            )
            session.add(pf)
            await session.flush()

            f = Entry(
                name=f"file_{j}.txt",
                type=EntryType.FILE,
                size=1024 * (j + 1),
                owner_id=user_id,
                parent_id=folder_id,
                policy_id=policy.id,
                physical_file_id=pf.id,
            )
            session.add(f)
            file_count += 1

    await session.commit()

    total_folders = depth + 1
    print(f"  测试数据: {total_folders} 个目录, {file_count} 个文件, 深度 {depth}")

    return user_id, root.id, deepest_folder_id


async def benchmark_get_by_path(session: AsyncSession, user_id: UUID, depth: int):
    """测试 get_by_path 性能（动态 JOIN 链）"""
    path = "/" + "/".join(f"level_{i}" for i in range(depth))

    # 预热
    await Entry.get_by_path(session, user_id, path)

    # 计时
    iterations = 50
    start = time.perf_counter()
    for _ in range(iterations):
        result = await Entry.get_by_path(session, user_id, path)
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / iterations) * 1000
    found = result is not None
    print(f"  get_by_path (depth={depth}): {avg_ms:.2f}ms/次 (x{iterations}), 找到={found}")


async def benchmark_get_by_path_old(session: AsyncSession, user_id: UUID, depth: int):
    """模拟旧版逐级 SELECT 路径解析"""
    parts = [f"level_{i}" for i in range(depth)]

    async def old_get_by_path(s: AsyncSession, uid: UUID, segments: list[str]) -> Entry | None:
        root = await Entry.get(s, (Entry.owner_id == uid) & (Entry.parent_id == None) & (Entry.deleted_at == None))
        if not root:
            return None
        current = root
        for part in segments:
            if not current:
                return None
            current = await Entry.get(
                s,
                (Entry.owner_id == uid) & (Entry.parent_id == current.id) & (Entry.name == part) & (Entry.deleted_at == None)
            )
        return current

    # 预热
    await old_get_by_path(session, user_id, parts)

    iterations = 50
    start = time.perf_counter()
    for _ in range(iterations):
        result = await old_get_by_path(session, user_id, parts)
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / iterations) * 1000
    found = result is not None
    print(f"  旧版逐级查 (depth={depth}): {avg_ms:.2f}ms/次 (x{iterations}), 找到={found}")


async def benchmark_collect_refs(session: AsyncSession, user_id: UUID, root_id: UUID):
    """测试 _collect_physical_file_refs 性能（递归 CTE）"""
    root = await Entry.get(session, Entry.id == root_id)
    if not root:
        print("  ERROR: 根目录不存在")
        return

    # 预热
    await root._collect_physical_file_refs(session, user_id)

    iterations = 20
    start = time.perf_counter()
    for _ in range(iterations):
        pf_ids, total_size = await root._collect_physical_file_refs(session, user_id)
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / iterations) * 1000
    print(f"  collect_refs (CTE): {avg_ms:.2f}ms/次 (x{iterations}), 文件数={len(pf_ids)}, 总大小={total_size}")


async def benchmark_is_ancestor(session: AsyncSession, root_id: UUID, deepest_id: UUID):
    """测试 is_ancestor_of 性能（递归 CTE）"""
    # 预热
    await Entry.is_ancestor_of(session, root_id, deepest_id)

    iterations = 50
    start = time.perf_counter()
    for _ in range(iterations):
        result = await Entry.is_ancestor_of(session, root_id, deepest_id)
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / iterations) * 1000
    print(f"  is_ancestor_of: {avg_ms:.2f}ms/次 (x{iterations}), 结果={result}")


async def main():
    print("=" * 60)
    print("DiskNext 文件 CRUD 性能基准测试")
    print("=" * 60)

    session_factory = await setup_db()

    for depth, breadth in [(5, 10), (10, 10), (20, 5), (50, 2)]:
        print(f"\n--- 场景: depth={depth}, breadth={breadth} ---")

        async with session_factory() as session:
            user_id, root_id, deepest_id = await create_test_data(session, depth, breadth)

        async with session_factory() as session:
            await benchmark_get_by_path(session, user_id, depth)
            await benchmark_get_by_path_old(session, user_id, depth)

        async with session_factory() as session:
            await benchmark_collect_refs(session, user_id, root_id)

        async with session_factory() as session:
            await benchmark_is_ancestor(session, root_id, deepest_id)

        # 清理
        async with session_factory() as session:
            from sqlmodel import text
            await session.exec(text("TRUNCATE file, physicalfile, \"user\", \"group\", policy CASCADE"))
            await session.commit()

    print("\n" + "=" * 60)
    print("基准测试完成")


if __name__ == "__main__":
    asyncio.run(main())
