"""
用户组模型 CRUD 测试（使用 db_session fixture）
"""
import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodels.group import Group


@pytest.mark.asyncio
async def test_group_curd(db_session: AsyncSession):
    """测试数据库的增删改查"""
    # 测试增 Create
    test_group = Group(name='test_group')
    created_group = await test_group.save(db_session)

    assert created_group is not None
    assert created_group.id is not None
    assert created_group.name == 'test_group'

    # 测试查 Read
    fetched_group = await Group.get(db_session, Group.id == created_group.id)
    assert fetched_group is not None
    assert fetched_group.id == created_group.id
    assert fetched_group.name == 'test_group'

    # 测试更新 Update
    update_data = Group(name="updated_group")
    updated_group = await fetched_group.update(db_session, update_data)

    assert updated_group is not None
    assert updated_group.id == fetched_group.id
    assert updated_group.name == 'updated_group'

    # 测试删除 Delete
    await Group.delete(db_session, instances=updated_group)
    deleted_group = await Group.get(db_session, Group.id == updated_group.id)
    assert deleted_group is None
