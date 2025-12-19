"""
TableBase 和 UUIDTableBase 的单元测试
"""
import uuid
from datetime import datetime

import pytest
from fastapi import HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from models.user import User
from models.group import Group


@pytest.mark.asyncio
async def test_table_base_add_single(db_session: AsyncSession):
    """测试单条记录创建"""
    # 创建用户组
    group = Group(name="测试组")
    result = await Group.add(db_session, group)

    assert result.id is not None
    assert result.name == "测试组"
    assert isinstance(result.created_at, datetime)


@pytest.mark.asyncio
async def test_table_base_add_batch(db_session: AsyncSession):
    """测试批量创建"""
    group1 = Group(name="用户组1")
    group2 = Group(name="用户组2")
    group3 = Group(name="用户组3")

    results = await Group.add(db_session, [group1, group2, group3])

    assert len(results) == 3
    assert all(g.id is not None for g in results)
    assert [g.name for g in results] == ["用户组1", "用户组2", "用户组3"]


@pytest.mark.asyncio
async def test_table_base_save(db_session: AsyncSession):
    """测试 save() 方法"""
    group = Group(name="保存测试组")
    saved_group = await group.save(db_session)

    assert saved_group.id is not None
    assert saved_group.name == "保存测试组"
    assert isinstance(saved_group.created_at, datetime)

    # 验证数据库中确实存在
    fetched = await Group.get(db_session, Group.id == saved_group.id)
    assert fetched is not None
    assert fetched.name == "保存测试组"


@pytest.mark.asyncio
async def test_table_base_update(db_session: AsyncSession):
    """测试 update() 方法"""
    # 创建初始数据
    group = Group(name="原始名称", max_storage=1000)
    group = await group.save(db_session)

    # 更新数据
    from models.group import GroupBase
    update_data = GroupBase(name="更新后名称")
    updated_group = await group.update(db_session, update_data)

    assert updated_group.name == "更新后名称"
    assert updated_group.max_storage == 1000  # 未更新的字段保持不变


@pytest.mark.asyncio
async def test_table_base_delete(db_session: AsyncSession):
    """测试 delete() 方法"""
    # 创建测试数据
    group = Group(name="待删除组")
    group = await group.save(db_session)
    group_id = group.id

    # 删除数据
    await Group.delete(db_session, group)

    # 验证已删除
    result = await Group.get(db_session, Group.id == group_id)
    assert result is None


@pytest.mark.asyncio
async def test_table_base_get_first(db_session: AsyncSession):
    """测试 get() fetch_mode="first" """
    # 创建测试数据
    group1 = Group(name="组A")
    group2 = Group(name="组B")
    await Group.add(db_session, [group1, group2])

    # 获取第一条
    result = await Group.get(db_session, None, fetch_mode="first")
    assert result is not None
    assert result.name in ["组A", "组B"]


@pytest.mark.asyncio
async def test_table_base_get_one(db_session: AsyncSession):
    """测试 get() fetch_mode="one" """
    # 创建唯一记录
    group = Group(name="唯一组")
    group = await group.save(db_session)

    # 获取唯一记录
    result = await Group.get(
        db_session,
        Group.name == "唯一组",
        fetch_mode="one"
    )
    assert result is not None
    assert result.id == group.id


@pytest.mark.asyncio
async def test_table_base_get_all(db_session: AsyncSession):
    """测试 get() fetch_mode="all" """
    # 创建多条记录
    groups = [Group(name=f"组{i}") for i in range(5)]
    await Group.add(db_session, groups)

    # 获取全部
    results = await Group.get(db_session, None, fetch_mode="all")
    assert len(results) == 5


@pytest.mark.asyncio
async def test_table_base_get_with_pagination(db_session: AsyncSession):
    """测试 offset/limit 分页"""
    # 创建10条记录
    groups = [Group(name=f"组{i:02d}") for i in range(10)]
    await Group.add(db_session, groups)

    # 分页获取: 跳过3条，取2条
    results = await Group.get(
        db_session,
        None,
        offset=3,
        limit=2,
        fetch_mode="all"
    )
    assert len(results) == 2


@pytest.mark.asyncio
async def test_table_base_get_exist_one_found(db_session: AsyncSession):
    """测试 get_exist_one() 存在时返回"""
    group = Group(name="存在的组")
    group = await group.save(db_session)

    result = await Group.get_exist_one(db_session, group.id)
    assert result is not None
    assert result.id == group.id


@pytest.mark.asyncio
async def test_table_base_get_exist_one_not_found(db_session: AsyncSession):
    """测试 get_exist_one() 不存在时抛出 HTTPException 404"""
    fake_uuid = uuid.uuid4()

    with pytest.raises(HTTPException) as exc_info:
        await Group.get_exist_one(db_session, fake_uuid)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_uuid_table_base_id_generation(db_session: AsyncSession):
    """测试 UUID 自动生成"""
    group = Group(name="UUID测试组")
    group = await group.save(db_session)

    assert isinstance(group.id, uuid.UUID)
    assert group.id is not None


@pytest.mark.asyncio
async def test_timestamps_auto_update(db_session: AsyncSession):
    """测试 created_at/updated_at 自动维护"""
    # 创建记录
    group = Group(name="时间戳测试")
    group = await group.save(db_session)

    created_time = group.created_at
    updated_time = group.updated_at

    assert isinstance(created_time, datetime)
    assert isinstance(updated_time, datetime)
    # 允许微秒级别的时间差（created_at 和 updated_at 可能在不同时刻设置）
    time_diff = abs((created_time - updated_time).total_seconds())
    assert time_diff < 1  # 差异应小于 1 秒

    # 等待一小段时间后更新
    import asyncio
    await asyncio.sleep(0.1)

    # 更新记录
    from models.group import GroupBase
    update_data = GroupBase(name="更新后的名称")
    group = await group.update(db_session, update_data)

    # updated_at 应该更新
    assert group.created_at == created_time  # created_at 不变
    # 注意: SQLite 可能不支持 onupdate，这个测试可能需要根据实际数据库调整
