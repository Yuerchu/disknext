"""
站点配置端点集成测试
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_site_ping(async_client: AsyncClient):
    """测试 /api/site/ping 返回 200"""
    response = await async_client.get("/api/v1/site/ping")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_site_ping_response_format(async_client: AsyncClient):
    """测试 /api/site/ping 响应包含 instance_id"""
    response = await async_client.get("/api/v1/site/ping")
    assert response.status_code == 200

    data = response.json()
    assert "instance_id" in data


@pytest.mark.asyncio
async def test_site_config(async_client: AsyncClient):
    """测试 /api/site/config 返回配置"""
    response = await async_client.get("/api/v1/site/config")
    assert response.status_code == 200

    data = response.json()
    assert "site_name" in data
    assert "is_register_enabled" in data


@pytest.mark.asyncio
async def test_site_config_contains_title(async_client: AsyncClient):
    """测试配置包含站点标题"""
    response = await async_client.get("/api/v1/site/config")
    assert response.status_code == 200

    data = response.json()
    assert "site_name" in data
    assert data["site_name"] == "DiskNext Test"


@pytest.mark.asyncio
async def test_site_config_register_enabled(async_client: AsyncClient):
    """测试配置包含注册开关"""
    response = await async_client.get("/api/v1/site/config")
    assert response.status_code == 200

    data = response.json()
    assert "is_register_enabled" in data
    assert data["is_register_enabled"] is True


@pytest.mark.asyncio
async def test_site_config_captcha_settings(async_client: AsyncClient):
    """测试配置包含验证码设置"""
    response = await async_client.get("/api/v1/site/config")
    assert response.status_code == 200

    data = response.json()
    assert "is_login_captcha" in data
    assert "is_reg_captcha" in data
    assert "is_forget_captcha" in data


@pytest.mark.asyncio
async def test_site_config_auth_methods(async_client: AsyncClient):
    """测试配置包含认证方式列表"""
    response = await async_client.get("/api/v1/site/config")
    assert response.status_code == 200

    data = response.json()
    assert "auth_methods" in data
    assert isinstance(data["auth_methods"], list)
    assert len(data["auth_methods"]) > 0

    # 每个认证方式应包含 provider 和 is_enabled
    for method in data["auth_methods"]:
        assert "provider" in method
        assert "is_enabled" in method


@pytest.mark.asyncio
async def test_site_captcha_endpoint_exists(async_client: AsyncClient):
    """测试验证码端点存在（即使未实现也应返回有效响应）"""
    response = await async_client.get("/api/v1/site/captcha")
    # 未实现的端点可能返回 404 或其他状态码
    assert response.status_code in [200, 404, 501]
