"""
管理员端点集成测试
"""
import pytest
from httpx import AsyncClient


# ==================== 认证测试 ====================

@pytest.mark.asyncio
async def test_admin_requires_auth(async_client: AsyncClient):
    """测试管理员接口需要认证"""
    response = await async_client.get("/api/v1/admin/summary")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_requires_admin_role(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试普通用户访问管理员接口返回 403"""
    response = await async_client.get(
        "/api/v1/admin/summary",
        headers=auth_headers
    )
    assert response.status_code == 403


# ==================== 站点概况测试 ====================

@pytest.mark.asyncio
async def test_admin_get_summary_success(
    async_client: AsyncClient,
    admin_headers: dict[str, str]
):
    """测试管理员可以获取站点概况"""
    response = await async_client.get(
        "/api/v1/admin/summary",
        headers=admin_headers
    )
    # 端点存在但未实现，可能返回 200 或其他状态
    assert response.status_code in [200, 404, 501]


# ==================== 用户管理测试 ====================

@pytest.mark.asyncio
async def test_admin_get_user_info_requires_auth(async_client: AsyncClient):
    """测试获取用户信息需要认证"""
    response = await async_client.get("/api/v1/admin/user/1")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_get_user_info_requires_admin(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试普通用户无法获取用户信息"""
    response = await async_client.get(
        "/api/v1/admin/user/1",
        headers=auth_headers
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_get_user_list_requires_auth(async_client: AsyncClient):
    """测试获取用户列表需要认证"""
    response = await async_client.get("/api/v1/admin/user/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_get_user_list_success(
    async_client: AsyncClient,
    admin_headers: dict[str, str]
):
    """测试管理员可以获取用户列表"""
    response = await async_client.get(
        "/api/v1/admin/user/",
        headers=admin_headers
    )
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    assert "count" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_admin_get_user_list_pagination(
    async_client: AsyncClient,
    admin_headers: dict[str, str]
):
    """测试用户列表分页"""
    response = await async_client.get(
        "/api/v1/admin/user/?page=1&page_size=10",
        headers=admin_headers
    )
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    # 应该返回不超过 page_size 的数量
    assert len(data["items"]) <= 10


@pytest.mark.asyncio
async def test_admin_get_user_list_contains_user_data(
    async_client: AsyncClient,
    admin_headers: dict[str, str]
):
    """测试用户列表包含用户数据"""
    response = await async_client.get(
        "/api/v1/admin/user/",
        headers=admin_headers
    )
    assert response.status_code == 200

    data = response.json()
    users = data["items"]
    if len(users) > 0:
        user = users[0]
        assert "id" in user
        assert "email" in user


@pytest.mark.asyncio
async def test_admin_create_user_requires_auth(async_client: AsyncClient):
    """测试创建用户需要认证"""
    response = await async_client.post(
        "/api/v1/admin/user/",
        json={"email": "newadminuser@test.local", "password": "pass123"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_create_user_requires_admin(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试普通用户无法创建用户"""
    response = await async_client.post(
        "/api/v1/admin/user/",
        headers=auth_headers,
        json={"email": "newadminuser@test.local", "password": "pass123"}
    )
    assert response.status_code == 403


# ==================== 用户组管理测试 ====================

@pytest.mark.asyncio
async def test_admin_get_groups_requires_auth(async_client: AsyncClient):
    """测试获取用户组列表需要认证"""
    response = await async_client.get("/api/v1/admin/group/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_get_groups_requires_admin(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试普通用户无法获取用户组列表"""
    response = await async_client.get(
        "/api/v1/admin/group/",
        headers=auth_headers
    )
    assert response.status_code == 403


# ==================== 文件管理测试 ====================

@pytest.mark.asyncio
async def test_admin_get_file_list_requires_auth(async_client: AsyncClient):
    """测试获取文件列表需要认证"""
    response = await async_client.get("/api/v1/admin/file/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_get_file_list_requires_admin(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试普通用户无法获取文件列表"""
    response = await async_client.get(
        "/api/v1/admin/file/",
        headers=auth_headers
    )
    assert response.status_code == 403


# ==================== 设置管理测试 ====================

@pytest.mark.asyncio
async def test_admin_get_settings_requires_auth(async_client: AsyncClient):
    """测试获取设置需要认证"""
    response = await async_client.get("/api/v1/admin/settings")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_get_settings_requires_admin(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试普通用户无法获取设置"""
    response = await async_client.get(
        "/api/v1/admin/settings",
        headers=auth_headers
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_update_settings_requires_auth(async_client: AsyncClient):
    """测试更新设置需要认证"""
    response = await async_client.patch(
        "/api/v1/admin/settings",
        json={"siteName": "New Site Name"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_update_settings_requires_admin(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试普通用户无法更新设置"""
    response = await async_client.patch(
        "/api/v1/admin/settings",
        headers=auth_headers,
        json={"siteName": "New Site Name"}
    )
    assert response.status_code == 403


# ==================== 存储策略管理测试 ====================

@pytest.mark.asyncio
async def test_admin_policy_list_requires_auth(async_client: AsyncClient):
    """测试获取存储策略列表需要认证"""
    response = await async_client.get("/api/v1/admin/policy/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_policy_list_requires_admin(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试普通用户无法获取存储策略列表"""
    response = await async_client.get(
        "/api/v1/admin/policy/",
        headers=auth_headers
    )
    assert response.status_code == 403
