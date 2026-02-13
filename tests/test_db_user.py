"""
用户模型 CRUD 测试（使用 db_session fixture）
"""
import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodels.group import Group
from sqlmodels.user import User


@pytest.mark.asyncio
async def test_user_curd(db_session: AsyncSession):
    """测试数据库的增删改查"""
    # 新建一个测试用户组
    test_user_group = Group(name='test_user_group')
    created_group = await test_user_group.save(db_session)

    test_user = User(
        email='test_user@test.local',
        group_id=created_group.id
    )

    # 测试增 Create
    created_user = await test_user.save(db_session)

    # 验证用户是否存在
    assert created_user.id is not None
    assert created_user.email == 'test_user@test.local'
    assert created_user.group_id == created_group.id

    # 测试查 Read
    fetched_user = await User.get(db_session, User.id == created_user.id)

    assert fetched_user is not None
    assert fetched_user.email == 'test_user@test.local'
    assert fetched_user.group_id == created_group.id

    # 测试改 Update
    from sqlmodels.user import UserBase
    update_data = UserBase(email="updated_user@test.local")
    updated_user = await fetched_user.update(db_session, update_data)

    assert updated_user is not None
    assert updated_user.email == 'updated_user@test.local'

    # 测试删除 Delete
    await User.delete(db_session, instances=updated_user)
    deleted_user = await User.get(db_session, User.id == updated_user.id)

    assert deleted_user is None
