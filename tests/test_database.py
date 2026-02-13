"""
数据库初始化和迁移测试
"""
import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker

from sqlmodels.database_connection import DatabaseManager


@pytest.mark.asyncio
async def test_database_manager_init():
    """测试 DatabaseManager 初始化"""
    await DatabaseManager.init(
        database_url="sqlite+aiosqlite:///:memory:",
        debug=True,
    )

    assert DatabaseManager.engine is not None
    assert DatabaseManager._async_session_factory is not None

    # 验证可以获取会话
    async for session in DatabaseManager.get_session():
        assert isinstance(session, AsyncSession)
        break

    await DatabaseManager.close()


@pytest.mark.asyncio
async def test_migration():
    """测试数据库迁移（创建默认数据）"""
    from sqlmodels.migration import migration

    await DatabaseManager.init(
        database_url="sqlite+aiosqlite:///:memory:",
        debug=False,
    )

    try:
        await migration()

        # 验证迁移后的数据
        async for session in DatabaseManager.get_session():
            from sqlmodels.setting import Setting, SettingsType
            from sqlmodels.group import Group

            # 验证设置项被创建
            secret_key = await Setting.get(
                session,
                (Setting.type == SettingsType.AUTH) & (Setting.name == "secret_key")
            )
            assert secret_key is not None

            # 验证默认用户组被创建
            admin_group = await Group.get(session, Group.name == "管理员")
            assert admin_group is not None
            assert admin_group.admin is True
            break
    finally:
        await DatabaseManager.close()
