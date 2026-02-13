"""
主程序基础端点测试
"""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlmodel.ext.asyncio.session import AsyncSession

from main import app


@pytest.mark.asyncio
async def test_read_main(db_session: AsyncSession):
    """测试 ping 端点"""
    from sqlmodels.database_connection import DatabaseManager

    async def override_get_session():
        yield db_session

    app.dependency_overrides[DatabaseManager.get_session] = override_get_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/site/ping")

            assert response.status_code == 200
    finally:
        app.dependency_overrides.clear()
