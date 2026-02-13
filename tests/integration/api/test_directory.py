"""
目录操作端点集成测试
"""
import pytest
from httpx import AsyncClient
from uuid import UUID


# ==================== 认证测试 ====================

@pytest.mark.asyncio
async def test_directory_requires_auth(async_client: AsyncClient):
    """测试获取目录需要认证"""
    response = await async_client.get("/api/v1/directory/")
    assert response.status_code == 401


# ==================== 获取目录测试 ====================

@pytest.mark.asyncio
async def test_directory_get_root(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试获取用户根目录"""
    response = await async_client.get(
        "/api/v1/directory/",
        headers=auth_headers
    )
    assert response.status_code == 200

    data = response.json()
    assert "id" in data
    assert "parent" in data
    assert "objects" in data
    assert "policy" in data
    assert data["parent"] is None  # 根目录的 parent 为 None


@pytest.mark.asyncio
async def test_directory_get_nested(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID]
):
    """测试获取嵌套目录"""
    response = await async_client.get(
        "/api/v1/directory/docs",
        headers=auth_headers
    )
    assert response.status_code == 200

    data = response.json()
    assert "id" in data
    assert "objects" in data


@pytest.mark.asyncio
async def test_directory_get_contains_children(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID]
):
    """测试目录包含子对象"""
    response = await async_client.get(
        "/api/v1/directory/docs",
        headers=auth_headers
    )
    assert response.status_code == 200

    data = response.json()
    objects = data["objects"]
    assert isinstance(objects, list)
    # docs 目录下应该有 images 文件夹和 readme.md 文件
    assert len(objects) >= 1


@pytest.mark.asyncio
async def test_directory_not_found(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试目录不存在返回 404"""
    response = await async_client.get(
        "/api/v1/directory/nonexistent",
        headers=auth_headers
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_directory_root_returns_200(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试根目录端点返回 200"""
    response = await async_client.get(
        "/api/v1/directory/",
        headers=auth_headers
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_directory_response_includes_policy(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试目录响应包含存储策略"""
    response = await async_client.get(
        "/api/v1/directory/",
        headers=auth_headers
    )
    assert response.status_code == 200

    data = response.json()
    assert "policy" in data
    policy = data["policy"]
    assert "id" in policy
    assert "name" in policy
    assert "type" in policy


# ==================== 创建目录测试 ====================

@pytest.mark.asyncio
async def test_directory_create_requires_auth(async_client: AsyncClient):
    """测试创建目录需要认证"""
    response = await async_client.post(
        "/api/v1/directory/",
        json={
            "parent_id": "00000000-0000-0000-0000-000000000000",
            "name": "newfolder"
        }
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_directory_create_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID]
):
    """测试成功创建目录"""
    parent_id = test_directory_structure["root_id"]

    response = await async_client.post(
        "/api/v1/directory/",
        headers=auth_headers,
        json={
            "parent_id": str(parent_id),
            "name": "newfolder"
        }
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_directory_create_duplicate_name(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID]
):
    """测试重名目录返回 409"""
    parent_id = test_directory_structure["root_id"]

    response = await async_client.post(
        "/api/v1/directory/",
        headers=auth_headers,
        json={
            "parent_id": str(parent_id),
            "name": "docs"  # 已存在的目录名
        }
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_directory_create_invalid_parent(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试无效父目录返回 404"""
    invalid_uuid = "00000000-0000-0000-0000-000000000001"

    response = await async_client.post(
        "/api/v1/directory/",
        headers=auth_headers,
        json={
            "parent_id": invalid_uuid,
            "name": "newfolder"
        }
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_directory_create_empty_name(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID]
):
    """测试空目录名返回 400"""
    parent_id = test_directory_structure["root_id"]

    response = await async_client.post(
        "/api/v1/directory/",
        headers=auth_headers,
        json={
            "parent_id": str(parent_id),
            "name": ""
        }
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_directory_create_name_with_slash(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID]
):
    """测试目录名包含斜杠返回 400"""
    parent_id = test_directory_structure["root_id"]

    response = await async_client.post(
        "/api/v1/directory/",
        headers=auth_headers,
        json={
            "parent_id": str(parent_id),
            "name": "invalid/name"
        }
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_directory_create_parent_is_file(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID]
):
    """测试父路径是文件返回 400"""
    file_id = test_directory_structure["file_id"]

    response = await async_client.post(
        "/api/v1/directory/",
        headers=auth_headers,
        json={
            "parent_id": str(file_id),
            "name": "newfolder"
        }
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_directory_create_other_user_parent(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str]
):
    """测试在他人目录下创建目录返回 404"""
    # 先用管理员账号获取管理员的根目录ID
    admin_response = await async_client.get(
        "/api/v1/directory/",
        headers=admin_headers
    )
    assert admin_response.status_code == 200
    admin_root_id = admin_response.json()["id"]

    # 普通用户尝试在管理员目录下创建文件夹
    response = await async_client.post(
        "/api/v1/directory/",
        headers=auth_headers,
        json={
            "parent_id": admin_root_id,
            "name": "hackfolder"
        }
    )
    assert response.status_code == 404
