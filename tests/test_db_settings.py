"""
设置模型 CRUD 测试（使用 db_session fixture）
"""
import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodels.setting import Setting, SettingsType


@pytest.mark.asyncio
async def test_settings_curd(db_session: AsyncSession):
    """测试设置的增删改查"""
    # 测试增 Create
    setting = Setting(
        type=SettingsType.BASIC,
        name='example_name',
        value='example_value',
    )
    setting = await setting.save(db_session)

    assert setting.id is not None

    # 测试查 Read
    fetched = await Setting.get(
        db_session,
        (Setting.type == SettingsType.BASIC) & (Setting.name == 'example_name')
    )

    assert fetched is not None
    assert fetched.value == 'example_value'

    # 测试改 Update
    update_data = Setting(type=SettingsType.BASIC, name='example_name', value='updated_value')
    updated = await fetched.update(db_session, update_data)

    assert updated is not None
    assert updated.value == 'updated_value'

    # 测试删 Delete
    await Setting.delete(db_session, instances=updated)
    deleted = await Setting.get(
        db_session,
        (Setting.type == SettingsType.BASIC) & (Setting.name == 'example_name')
    )

    assert deleted is None
