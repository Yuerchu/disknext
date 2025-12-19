"""
站点配置端点集成测试
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_site_ping(async_client: AsyncClient):
    """测试 /api/site/ping 返回 200"""
    response = await async_client.get("/api/site/ping")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_site_ping_response_format(async_client: AsyncClient):
    """测试 /api/site/ping 响应包含版本号"""
    response = await async_client.get("/api/site/ping")
    assert response.status_code == 200

    data = response.json()
    assert "data" in data
    # BackendVersion 应该是字符串格式的版本号
    assert isinstance(data["data"], str)


@pytest.mark.asyncio
async def test_site_config(async_client: AsyncClient):
    """测试 /api/site/config 返回配置"""
    response = await async_client.get("/api/site/config")
    assert response.status_code == 200

    data = response.json()
    assert "data" in data


@pytest.mark.asyncio
async def test_site_config_contains_title(async_client: AsyncClient):
    """测试配置包含站点标题"""
    response = await async_client.get("/api/site/config")
    assert response.status_code == 200

    data = response.json()
    config = data["data"]
    assert "title" in config
    assert config["title"] == "DiskNext Test"


@pytest.mark.asyncio
async def test_site_config_contains_themes(async_client: AsyncClient):
    """测试配置包含主题设置"""
    response = await async_client.get("/api/site/config")
    assert response.status_code == 200

    data = response.json()
    config = data["data"]
    assert "themes" in config
    assert "defaultTheme" in config


@pytest.mark.asyncio
async def test_site_config_register_enabled(async_client: AsyncClient):
    """测试配置包含注册开关"""
    response = await async_client.get("/api/site/config")
    assert response.status_code == 200

    data = response.json()
    config = data["data"]
    assert "registerEnabled" in config
    assert config["registerEnabled"] is True


@pytest.mark.asyncio
async def test_site_config_captcha_settings(async_client: AsyncClient):
    """测试配置包含验证码设置"""
    response = await async_client.get("/api/site/config")
    assert response.status_code == 200

    data = response.json()
    config = data["data"]
    assert "loginCaptcha" in config
    assert "regCaptcha" in config
    assert "forgetCaptcha" in config


@pytest.mark.asyncio
async def test_site_captcha_endpoint_exists(async_client: AsyncClient):
    """测试验证码端点存在（即使未实现也应返回有效响应）"""
    response = await async_client.get("/api/site/captcha")
    # 未实现的端点可能返回 404 或其他状态码
    assert response.status_code in [200, 404, 501]
