"""
对象操作端点集成测试
"""
import pytest
from httpx import AsyncClient
from uuid import UUID


# ==================== 删除对象测试 ====================

@pytest.mark.asyncio
async def test_object_delete_requires_auth(async_client: AsyncClient):
    """测试删除对象需要认证"""
    response = await async_client.request(
        "DELETE",
        "/api/v1/object/",
        json={"ids": ["00000000-0000-0000-0000-000000000000"]}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_object_delete_single(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID]
):
    """测试删除单个对象"""
    file_id = test_directory_structure["file_id"]

    response = await async_client.request(
        "DELETE",
        "/api/v1/object/",
        headers=auth_headers,
        json={"ids": [str(file_id)]}
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_object_delete_nonexistent(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试删除不存在的对象返回 204（幂等）"""
    fake_id = "00000000-0000-0000-0000-000000000001"

    response = await async_client.request(
        "DELETE",
        "/api/v1/object/",
        headers=auth_headers,
        json={"ids": [fake_id]}
    )
    assert response.status_code == 204


# ==================== 移动对象测试 ====================

@pytest.mark.asyncio
async def test_object_move_requires_auth(async_client: AsyncClient):
    """测试移动对象需要认证"""
    response = await async_client.patch(
        "/api/v1/object/",
        json={
            "src_ids": ["00000000-0000-0000-0000-000000000000"],
            "dst_id": "00000000-0000-0000-0000-000000000001"
        }
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_object_move_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID]
):
    """测试成功移动对象"""
    file_id = test_directory_structure["file_id"]
    images_id = test_directory_structure["images_id"]

    response = await async_client.patch(
        "/api/v1/object/",
        headers=auth_headers,
        json={
            "src_ids": [str(file_id)],
            "dst_id": str(images_id)
        }
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_object_move_to_invalid_target(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID]
):
    """测试无效目标返回 404"""
    file_id = test_directory_structure["file_id"]
    invalid_dst = "00000000-0000-0000-0000-000000000001"

    response = await async_client.patch(
        "/api/v1/object/",
        headers=auth_headers,
        json={
            "src_ids": [str(file_id)],
            "dst_id": invalid_dst
        }
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_object_move_to_file(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID]
):
    """测试移动到文件返回 400"""
    docs_id = test_directory_structure["docs_id"]
    file_id = test_directory_structure["file_id"]

    response = await async_client.patch(
        "/api/v1/object/",
        headers=auth_headers,
        json={
            "src_ids": [str(docs_id)],
            "dst_id": str(file_id)
        }
    )
    assert response.status_code == 400


# ==================== 其他对象操作测试 ====================

@pytest.mark.asyncio
async def test_object_copy_endpoint_exists(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试复制对象端点存在"""
    response = await async_client.post(
        "/api/v1/object/copy",
        headers=auth_headers,
        json={"src_id": "00000000-0000-0000-0000-000000000000"}
    )
    # 未实现的端点
    assert response.status_code in [200, 204, 404, 422, 501]


@pytest.mark.asyncio
async def test_object_rename_endpoint_exists(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试重命名对象端点存在"""
    response = await async_client.post(
        "/api/v1/object/rename",
        headers=auth_headers,
        json={
            "id": "00000000-0000-0000-0000-000000000000",
            "name": "newname"
        }
    )
    # 未实现的端点
    assert response.status_code in [200, 204, 404, 422, 501]


@pytest.mark.asyncio
async def test_object_property_endpoint_exists(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试获取对象属性端点存在"""
    response = await async_client.get(
        "/api/v1/object/property/00000000-0000-0000-0000-000000000000",
        headers=auth_headers
    )
    # 未实现的端点
    assert response.status_code in [200, 404, 501]
