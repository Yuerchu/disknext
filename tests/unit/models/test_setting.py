"""
Setting 模型的单元测试
"""
import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodels.setting import Setting, SettingsType


@pytest.mark.asyncio
async def test_setting_create(db_session: AsyncSession):
    """测试创建设置"""
    setting = Setting(
        type=SettingsType.BASIC,
        name="site_name",
        value="DiskNext Test"
    )
    setting = await setting.save(db_session)

    assert setting.id is not None
    assert setting.type == SettingsType.BASIC
    assert setting.name == "site_name"
    assert setting.value == "DiskNext Test"


@pytest.mark.asyncio
async def test_setting_unique_type_name(db_session: AsyncSession):
    """测试 type+name 唯一约束"""
    # 创建第一个设置
    setting1 = Setting(
        type=SettingsType.AUTH,
        name="secret_key",
        value="key1"
    )
    await setting1.save(db_session)

    # 尝试创建相同 type+name 的设置
    setting2 = Setting(
        type=SettingsType.AUTH,
        name="secret_key",
        value="key2"
    )

    with pytest.raises(IntegrityError):
        await setting2.save(db_session)


@pytest.mark.asyncio
async def test_setting_unique_type_name_different_type(db_session: AsyncSession):
    """测试不同 type 可以有相同 name"""
    # 创建两个不同 type 但相同 name 的设置
    setting1 = Setting(
        type=SettingsType.AUTH,
        name="timeout",
        value="3600"
    )
    await setting1.save(db_session)

    setting2 = Setting(
        type=SettingsType.TIMEOUT,
        name="timeout",
        value="7200"
    )
    setting2 = await setting2.save(db_session)

    # 应该都能成功创建
    assert setting1.id is not None
    assert setting2.id is not None
    assert setting1.id != setting2.id


@pytest.mark.asyncio
async def test_settings_type_enum(db_session: AsyncSession):
    """测试 SettingsType 枚举"""
    # 测试各种设置类型
    types_to_test = [
        SettingsType.ARIA2,
        SettingsType.AUTH,
        SettingsType.AUTHN,
        SettingsType.AVATAR,
        SettingsType.BASIC,
        SettingsType.CAPTCHA,
        SettingsType.CRON,
        SettingsType.FILE_EDIT,
        SettingsType.LOGIN,
        SettingsType.MAIL,
        SettingsType.MOBILE,
        SettingsType.PREVIEW,
        SettingsType.SHARE,
    ]

    for idx, setting_type in enumerate(types_to_test):
        setting = Setting(
            type=setting_type,
            name=f"test_{idx}",
            value=f"value_{idx}"
        )
        setting = await setting.save(db_session)

        assert setting.type == setting_type


@pytest.mark.asyncio
async def test_setting_update_value(db_session: AsyncSession):
    """测试更新设置值"""
    # 创建设置
    setting = Setting(
        type=SettingsType.BASIC,
        name="app_version",
        value="1.0.0"
    )
    setting = await setting.save(db_session)

    # 更新值
    from sqlmodel_ext import SQLModelBase

    class SettingUpdate(SQLModelBase):
        value: str | None = None

    update_data = SettingUpdate(value="1.0.1")
    setting = await setting.update(db_session, update_data)

    assert setting.value == "1.0.1"


@pytest.mark.asyncio
async def test_setting_nullable_value(db_session: AsyncSession):
    """测试 value 可为空"""
    setting = Setting(
        type=SettingsType.MAIL,
        name="smtp_server",
        value=None
    )
    setting = await setting.save(db_session)

    assert setting.value is None


@pytest.mark.asyncio
async def test_setting_get_by_type_and_name(db_session: AsyncSession):
    """测试通过 type 和 name 获取设置"""
    # 创建多个设置
    setting1 = Setting(
        type=SettingsType.AUTH,
        name="jwt_secret",
        value="secret123"
    )
    await setting1.save(db_session)

    setting2 = Setting(
        type=SettingsType.AUTH,
        name="jwt_expiry",
        value="3600"
    )
    await setting2.save(db_session)

    # 查询特定设置
    result = await Setting.get(
        db_session,
        (Setting.type == SettingsType.AUTH) & (Setting.name == "jwt_secret")
    )

    assert result is not None
    assert result.value == "secret123"


@pytest.mark.asyncio
async def test_setting_get_all_by_type(db_session: AsyncSession):
    """测试获取某个类型的所有设置"""
    # 创建多个 BASIC 类型设置
    settings_data = [
        ("title", "DiskNext"),
        ("description", "Cloud Storage"),
        ("version", "2.0.0"),
    ]

    for name, value in settings_data:
        setting = Setting(
            type=SettingsType.BASIC,
            name=name,
            value=value
        )
        await setting.save(db_session)

    # 创建其他类型设置
    other_setting = Setting(
        type=SettingsType.MAIL,
        name="smtp_port",
        value="587"
    )
    await other_setting.save(db_session)

    # 查询所有 BASIC 类型设置
    results = await Setting.get(
        db_session,
        Setting.type == SettingsType.BASIC,
        fetch_mode="all"
    )

    assert len(results) == 3
    names = {s.name for s in results}
    assert names == {"title", "description", "version"}
