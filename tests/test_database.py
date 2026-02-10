import pytest

@pytest.mark.asyncio
async def test_initialize_db():
    """测试创建数据库结构"""
    from sqlmodels import database
    
    await database.init_db(url='sqlite:///:memory:')

@pytest.fixture
async def db_session():
    """测试获取数据库连接Session"""
    from sqlmodels import database
    
    await database.init_db(url='sqlite:///:memory:')
    
    async for session in database.get_session():
        yield session

@pytest.mark.asyncio
async def test_migration():
    """测试数据库创建并初始化配置"""
    from sqlmodels import migration
    from sqlmodels import database
    
    await database.init_db(url='sqlite:///:memory:')
    
    await migration.migration()