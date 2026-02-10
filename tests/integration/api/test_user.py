"""
用户相关端点集成测试
"""
import pytest
from httpx import AsyncClient


# ==================== 登录测试 ====================

@pytest.mark.asyncio
async def test_user_login_success(
    async_client: AsyncClient,
    test_user_info: dict[str, str]
):
    """测试成功登录"""
    response = await async_client.post(
        "/api/user/session",
        data={
            "username": test_user_info["email"],
            "password": test_user_info["password"],
        }
    )
    assert response.status_code == 200

    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert "access_expires" in data
    assert "refresh_expires" in data


@pytest.mark.asyncio
async def test_user_login_wrong_password(
    async_client: AsyncClient,
    test_user_info: dict[str, str]
):
    """测试密码错误返回 401"""
    response = await async_client.post(
        "/api/user/session",
        data={
            "username": test_user_info["email"],
            "password": "wrongpassword",
        }
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_user_login_nonexistent_user(async_client: AsyncClient):
    """测试不存在的用户返回 401"""
    response = await async_client.post(
        "/api/user/session",
        data={
            "username": "nonexistent@test.local",
            "password": "anypassword",
        }
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_user_login_user_banned(
    async_client: AsyncClient,
    banned_user_info: dict[str, str]
):
    """测试封禁用户返回 403"""
    response = await async_client.post(
        "/api/user/session",
        data={
            "username": banned_user_info["email"],
            "password": banned_user_info["password"],
        }
    )
    assert response.status_code == 403


# ==================== 注册测试 ====================

@pytest.mark.asyncio
async def test_user_register_success(async_client: AsyncClient):
    """测试成功注册"""
    response = await async_client.post(
        "/api/user/",
        json={
            "email": "newuser@test.local",
            "password": "newpass123",
        }
    )
    assert response.status_code == 200

    data = response.json()
    assert "data" in data
    assert "user_id" in data["data"]
    assert "email" in data["data"]
    assert data["data"]["email"] == "newuser@test.local"


@pytest.mark.asyncio
async def test_user_register_duplicate_email(
    async_client: AsyncClient,
    test_user_info: dict[str, str]
):
    """测试重复邮箱返回 400"""
    response = await async_client.post(
        "/api/user/",
        json={
            "email": test_user_info["email"],
            "password": "anypassword",
        }
    )
    assert response.status_code == 400


# ==================== 用户信息测试 ====================

@pytest.mark.asyncio
async def test_user_me_requires_auth(async_client: AsyncClient):
    """测试 /api/user/me 需要认证"""
    response = await async_client.get("/api/user/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_user_me_with_invalid_token(async_client: AsyncClient):
    """测试无效token返回 401"""
    response = await async_client.get(
        "/api/user/me",
        headers={"Authorization": "Bearer invalid_token"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_user_me_returns_user_info(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试返回用户信息"""
    response = await async_client.get("/api/user/me", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert "data" in data
    user_data = data["data"]
    assert "id" in user_data
    assert "email" in user_data
    assert user_data["email"] == "testuser@test.local"
    assert "group" in user_data
    assert "tags" in user_data


@pytest.mark.asyncio
async def test_user_me_contains_group_info(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试用户信息包含用户组"""
    response = await async_client.get("/api/user/me", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    user_data = data["data"]
    assert user_data["group"] is not None
    assert "name" in user_data["group"]


# ==================== 存储信息测试 ====================

@pytest.mark.asyncio
async def test_user_storage_requires_auth(async_client: AsyncClient):
    """测试 /api/user/storage 需要认证"""
    response = await async_client.get("/api/user/storage")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_user_storage_info(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试返回存储信息"""
    response = await async_client.get("/api/user/storage", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert "data" in data
    storage_data = data["data"]
    assert "used" in storage_data
    assert "free" in storage_data
    assert "total" in storage_data
    assert storage_data["total"] == storage_data["used"] + storage_data["free"]


# ==================== 两步验证测试 ====================

@pytest.mark.asyncio
async def test_user_2fa_init_requires_auth(async_client: AsyncClient):
    """测试获取2FA初始化信息需要认证"""
    response = await async_client.get("/api/user/settings/2fa")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_user_2fa_init(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试获取2FA初始化信息"""
    response = await async_client.get(
        "/api/user/settings/2fa",
        headers=auth_headers
    )
    assert response.status_code == 200

    data = response.json()
    assert "data" in data
    # 应该包含二维码URL和密钥
    assert isinstance(data["data"], dict)


@pytest.mark.asyncio
async def test_user_2fa_enable_requires_auth(async_client: AsyncClient):
    """测试启用2FA需要认证"""
    response = await async_client.post(
        "/api/user/settings/2fa",
        params={"setup_token": "fake_token", "code": "123456"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_user_2fa_enable_invalid_token(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试无效的setup_token返回 400"""
    response = await async_client.post(
        "/api/user/settings/2fa",
        params={"setup_token": "invalid_token", "code": "123456"},
        headers=auth_headers
    )
    assert response.status_code == 400


# ==================== 用户设置测试 ====================

@pytest.mark.asyncio
async def test_user_settings_requires_auth(async_client: AsyncClient):
    """测试获取用户设置需要认证"""
    response = await async_client.get("/api/user/settings/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_user_settings_returns_data(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试返回用户设置"""
    response = await async_client.get(
        "/api/user/settings/",
        headers=auth_headers
    )
    assert response.status_code == 200

    data = response.json()
    assert "data" in data


# ==================== WebAuthn 测试 ====================

@pytest.mark.asyncio
async def test_user_authn_start_requires_auth(async_client: AsyncClient):
    """测试WebAuthn初始化需要认证"""
    response = await async_client.put("/api/user/authn/start")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_user_authn_start_disabled(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试WebAuthn未启用时返回 400"""
    response = await async_client.put(
        "/api/user/authn/start",
        headers=auth_headers
    )
    # WebAuthn 在测试环境中未启用
    assert response.status_code == 400
