"""
认证中间件集成测试
"""
import pytest
from httpx import AsyncClient
from datetime import timedelta

from utils.JWT import JWT


# ==================== AuthRequired 测试 ====================

@pytest.mark.asyncio
async def test_auth_required_no_token(async_client: AsyncClient):
    """测试无token返回 401"""
    response = await async_client.get("/api/user/me")
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers


@pytest.mark.asyncio
async def test_auth_required_invalid_token(async_client: AsyncClient):
    """测试无效token返回 401"""
    response = await async_client.get(
        "/api/user/me",
        headers={"Authorization": "Bearer invalid_token_string"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_auth_required_malformed_token(async_client: AsyncClient):
    """测试格式错误的token返回 401"""
    response = await async_client.get(
        "/api/user/me",
        headers={"Authorization": "InvalidFormat"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_auth_required_expired_token(
    async_client: AsyncClient,
    expired_token: str
):
    """测试过期token返回 401"""
    response = await async_client.get(
        "/api/user/me",
        headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_auth_required_valid_token(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试有效token通过认证"""
    response = await async_client.get(
        "/api/user/me",
        headers=auth_headers
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_auth_required_token_without_sub(async_client: AsyncClient):
    """测试缺少sub字段的token返回 401"""
    token, _ = JWT.create_access_token(
        data={"other_field": "value"},
        expires_delta=timedelta(hours=1)
    )

    response = await async_client.get(
        "/api/user/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_auth_required_nonexistent_user_token(async_client: AsyncClient):
    """测试用户不存在的token返回 401"""
    token, _ = JWT.create_access_token(
        data={"sub": "nonexistent_user@test.local"},
        expires_delta=timedelta(hours=1)
    )

    response = await async_client.get(
        "/api/user/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


# ==================== AdminRequired 测试 ====================

@pytest.mark.asyncio
async def test_admin_required_no_auth(async_client: AsyncClient):
    """测试管理员端点无认证返回 401"""
    response = await async_client.get("/api/admin/summary")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_required_non_admin(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试非管理员返回 403"""
    response = await async_client.get(
        "/api/admin/summary",
        headers=auth_headers
    )
    assert response.status_code == 403
    data = response.json()
    assert "detail" in data
    assert data["detail"] == "Admin Required"


@pytest.mark.asyncio
async def test_admin_required_admin(
    async_client: AsyncClient,
    admin_headers: dict[str, str]
):
    """测试管理员通过认证"""
    response = await async_client.get(
        "/api/admin/summary",
        headers=admin_headers
    )
    # 端点可能未实现，但应该通过认证检查
    assert response.status_code != 403
    assert response.status_code != 401


@pytest.mark.asyncio
async def test_admin_required_on_user_list(
    async_client: AsyncClient,
    admin_headers: dict[str, str]
):
    """测试管理员可以访问用户列表"""
    response = await async_client.get(
        "/api/admin/user/list",
        headers=admin_headers
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_admin_required_on_settings(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str]
):
    """测试管理员可以访问设置，普通用户不能"""
    # 普通用户
    user_response = await async_client.get(
        "/api/admin/settings",
        headers=auth_headers
    )
    assert user_response.status_code == 403

    # 管理员
    admin_response = await async_client.get(
        "/api/admin/settings",
        headers=admin_headers
    )
    assert admin_response.status_code != 403


# ==================== 认证装饰器应用测试 ====================

@pytest.mark.asyncio
async def test_auth_on_directory_endpoint(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试目录端点应用认证"""
    # 无认证
    response_no_auth = await async_client.get("/api/directory/")
    assert response_no_auth.status_code == 401

    # 有认证
    response_with_auth = await async_client.get(
        "/api/directory/",
        headers=auth_headers
    )
    assert response_with_auth.status_code == 200


@pytest.mark.asyncio
async def test_auth_on_object_endpoint(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试对象端点应用认证"""
    # 无认证
    response_no_auth = await async_client.delete(
        "/api/object/",
        json={"ids": ["00000000-0000-0000-0000-000000000000"]}
    )
    assert response_no_auth.status_code == 401

    # 有认证
    response_with_auth = await async_client.delete(
        "/api/object/",
        headers=auth_headers,
        json={"ids": ["00000000-0000-0000-0000-000000000000"]}
    )
    assert response_with_auth.status_code == 200


@pytest.mark.asyncio
async def test_auth_on_storage_endpoint(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试存储端点应用认证"""
    # 无认证
    response_no_auth = await async_client.get("/api/user/storage")
    assert response_no_auth.status_code == 401

    # 有认证
    response_with_auth = await async_client.get(
        "/api/user/storage",
        headers=auth_headers
    )
    assert response_with_auth.status_code == 200


# ==================== Token 刷新测试 ====================

@pytest.mark.asyncio
async def test_refresh_token_format(test_user_info: dict[str, str]):
    """测试刷新token格式正确"""
    refresh_token, _ = JWT.create_refresh_token(
        data={"sub": test_user_info["email"]},
        expires_delta=timedelta(days=7)
    )

    assert isinstance(refresh_token, str)
    assert len(refresh_token) > 0


@pytest.mark.asyncio
async def test_access_token_format(test_user_info: dict[str, str]):
    """测试访问token格式正确"""
    access_token, expires = JWT.create_access_token(
        data={"sub": test_user_info["email"]},
        expires_delta=timedelta(hours=1)
    )

    assert isinstance(access_token, str)
    assert len(access_token) > 0
    assert expires is not None
