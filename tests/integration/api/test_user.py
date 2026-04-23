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
        "/api/v1/user/session",
        json={
            "provider": "email_password",
            "identifier": test_user_info["email"],
            "credential": test_user_info["password"],
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
        "/api/v1/user/session",
        json={
            "provider": "email_password",
            "identifier": test_user_info["email"],
            "credential": "wrongpassword",
        }
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_user_login_nonexistent_user(async_client: AsyncClient):
    """测试不存在的用户返回 401"""
    response = await async_client.post(
        "/api/v1/user/session",
        json={
            "provider": "email_password",
            "identifier": "nonexistent@example.com",
            "credential": "anypassword",
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
        "/api/v1/user/session",
        json={
            "provider": "email_password",
            "identifier": banned_user_info["email"],
            "credential": banned_user_info["password"],
        }
    )
    assert response.status_code == 403


# ==================== 注册测试 ====================

@pytest.mark.asyncio
async def test_user_register_success(async_client: AsyncClient):
    """测试成功注册"""
    response = await async_client.post(
        "/api/v1/user/",
        json={
            "provider": "email_password",
            "identifier": "newuser@example.com",
            "credential": "newpass123",
        }
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_user_register_duplicate_email(
    async_client: AsyncClient,
    test_user_info: dict[str, str]
):
    """测试重复邮箱返回 409"""
    response = await async_client.post(
        "/api/v1/user/",
        json={
            "provider": "email_password",
            "identifier": test_user_info["email"],
            "credential": "anypassword",
        }
    )
    assert response.status_code == 409


# ==================== 用户信息测试 ====================

@pytest.mark.asyncio
async def test_user_me_requires_auth(async_client: AsyncClient):
    """测试 /api/user/me 需要认证"""
    response = await async_client.get("/api/v1/user/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_user_me_with_invalid_token(async_client: AsyncClient):
    """测试无效token返回 401"""
    response = await async_client.get(
        "/api/v1/user/me",
        headers={"Authorization": "Bearer invalid_token"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_user_me_returns_user_info(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试返回用户信息"""
    response = await async_client.get("/api/v1/user/me", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert "id" in data
    assert "email" in data
    assert data["email"] == "testuser@example.com"
    assert "group" in data
    assert "tags" in data


@pytest.mark.asyncio
async def test_user_me_contains_group_info(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试用户信息包含用户组"""
    response = await async_client.get("/api/v1/user/me", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["group"] is not None
    assert "name" in data["group"]


# ==================== 存储信息测试 ====================

@pytest.mark.asyncio
async def test_user_storage_requires_auth(async_client: AsyncClient):
    """测试 /api/user/storage 需要认证"""
    response = await async_client.get("/api/v1/user/storage")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_user_storage_info(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试返回存储信息"""
    response = await async_client.get("/api/v1/user/storage", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert "used" in data
    assert "free" in data
    assert "total" in data
    assert data["total"] == data["used"] + data["free"]


# ==================== 两步验证测试 ====================

@pytest.mark.asyncio
async def test_user_2fa_init_requires_auth(async_client: AsyncClient):
    """测试获取2FA初始化信息需要认证"""
    response = await async_client.get("/api/v1/user/settings/2fa")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_user_2fa_init(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试获取2FA初始化信息"""
    response = await async_client.get(
        "/api/v1/user/settings/2fa",
        headers=auth_headers
    )
    assert response.status_code == 200

    data = response.json()
    # TwoFactorResponse 应包含 setup_token 和 uri
    assert "setup_token" in data
    assert "uri" in data


@pytest.mark.asyncio
async def test_user_2fa_enable_requires_auth(async_client: AsyncClient):
    """测试启用2FA需要认证"""
    response = await async_client.post(
        "/api/v1/user/settings/2fa",
        json={"setup_token": "fake_token", "code": "123456"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_user_2fa_enable_invalid_token(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试无效的setup_token返回 400"""
    response = await async_client.post(
        "/api/v1/user/settings/2fa",
        json={"setup_token": "invalid_token", "code": "123456"},
        headers=auth_headers
    )
    assert response.status_code == 400


# ==================== 用户设置测试 ====================

@pytest.mark.asyncio
async def test_user_settings_requires_auth(async_client: AsyncClient):
    """测试获取用户设置需要认证"""
    response = await async_client.get("/api/v1/user/settings/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_user_settings_returns_data(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试返回用户设置"""
    response = await async_client.get(
        "/api/v1/user/settings/",
        headers=auth_headers
    )
    assert response.status_code == 200

    data = response.json()
    assert "id" in data
    assert "email" in data


# ==================== WebAuthn 测试 ====================

@pytest.mark.asyncio
async def test_user_authn_start_requires_auth(async_client: AsyncClient):
    """测试WebAuthn初始化需要认证"""
    response = await async_client.post("/api/v1/user/authn/registration")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_user_authn_start_disabled(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试WebAuthn未启用时返回 400"""
    response = await async_client.post(
        "/api/v1/user/authn/registration",
        headers=auth_headers
    )
    # WebAuthn 在测试环境中未启用
    assert response.status_code == 400
