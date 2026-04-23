"""
对象元数据端点集成测试
"""
import pytest
from httpx import AsyncClient
from uuid import UUID, uuid4

from sqlmodels import EntryMetadata


# ==================== 获取元数据测试 ====================

@pytest.mark.asyncio
async def test_get_metadata_requires_auth(async_client: AsyncClient):
    """测试获取元数据需要认证"""
    fake_id = str(uuid4())
    response = await async_client.get(f"/api/v1/object/{fake_id}/metadata")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_metadata_empty(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID],
):
    """测试获取无元数据的对象"""
    file_id = test_directory_structure["file_id"]
    response = await async_client.get(
        f"/api/v1/object/{file_id}/metadata",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["metadatas"] == {}


@pytest.mark.asyncio
async def test_get_metadata_with_entries(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID],
    initialized_db,
):
    """测试获取有元数据的对象"""
    file_id = test_directory_structure["file_id"]

    # 直接写入元数据
    entries = [
        EntryMetadata(file_id=file_id, name="exif:width", value="1920", is_public=True),
        EntryMetadata(file_id=file_id, name="exif:height", value="1080", is_public=True),
        EntryMetadata(file_id=file_id, name="sys:extract_status", value="done", is_public=False),
    ]
    for entry in entries:
        initialized_db.add(entry)
    await initialized_db.commit()

    response = await async_client.get(
        f"/api/v1/object/{file_id}/metadata",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    # sys: 命名空间应被过滤
    assert "exif:width" in data["metadatas"]
    assert "exif:height" in data["metadatas"]
    assert "sys:extract_status" not in data["metadatas"]
    assert data["metadatas"]["exif:width"] == "1920"


@pytest.mark.asyncio
async def test_get_metadata_ns_filter(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID],
    initialized_db,
):
    """测试按命名空间过滤元数据"""
    file_id = test_directory_structure["file_id"]

    entries = [
        EntryMetadata(file_id=file_id, name="exif:width", value="1920", is_public=True),
        EntryMetadata(file_id=file_id, name="music:title", value="Test Song", is_public=True),
    ]
    for entry in entries:
        initialized_db.add(entry)
    await initialized_db.commit()

    # 只获取 exif 命名空间
    response = await async_client.get(
        f"/api/v1/object/{file_id}/metadata?ns=exif",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "exif:width" in data["metadatas"]
    assert "music:title" not in data["metadatas"]


@pytest.mark.asyncio
async def test_get_metadata_nonexistent_object(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """测试获取不存在对象的元数据"""
    fake_id = str(uuid4())
    response = await async_client.get(
        f"/api/v1/object/{fake_id}/metadata",
        headers=auth_headers,
    )
    assert response.status_code == 404


# ==================== 更新元数据测试 ====================

@pytest.mark.asyncio
async def test_patch_metadata_requires_auth(async_client: AsyncClient):
    """测试更新元数据需要认证"""
    fake_id = str(uuid4())
    response = await async_client.patch(
        f"/api/v1/object/{fake_id}/metadata",
        json={"patches": [{"key": "custom:tag", "value": "test"}]},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_patch_metadata_set_custom(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID],
):
    """测试设置自定义元数据"""
    file_id = test_directory_structure["file_id"]

    response = await async_client.patch(
        f"/api/v1/object/{file_id}/metadata",
        headers=auth_headers,
        json={
            "patches": [
                {"key": "custom:tag1", "value": "旅游"},
                {"key": "custom:tag2", "value": "风景"},
            ]
        },
    )
    assert response.status_code == 204

    # 验证已写入
    get_response = await async_client.get(
        f"/api/v1/object/{file_id}/metadata?ns=custom",
        headers=auth_headers,
    )
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["metadatas"]["custom:tag1"] == "旅游"
    assert data["metadatas"]["custom:tag2"] == "风景"


@pytest.mark.asyncio
async def test_patch_metadata_update_existing(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID],
):
    """测试更新已有的元数据"""
    file_id = test_directory_structure["file_id"]

    # 先创建
    await async_client.patch(
        f"/api/v1/object/{file_id}/metadata",
        headers=auth_headers,
        json={"patches": [{"key": "custom:note", "value": "旧值"}]},
    )

    # 再更新
    response = await async_client.patch(
        f"/api/v1/object/{file_id}/metadata",
        headers=auth_headers,
        json={"patches": [{"key": "custom:note", "value": "新值"}]},
    )
    assert response.status_code == 204

    # 验证已更新
    get_response = await async_client.get(
        f"/api/v1/object/{file_id}/metadata?ns=custom",
        headers=auth_headers,
    )
    data = get_response.json()
    assert data["metadatas"]["custom:note"] == "新值"


@pytest.mark.asyncio
async def test_patch_metadata_delete(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID],
):
    """测试删除元数据条目"""
    file_id = test_directory_structure["file_id"]

    # 先创建
    await async_client.patch(
        f"/api/v1/object/{file_id}/metadata",
        headers=auth_headers,
        json={"patches": [{"key": "custom:to_delete", "value": "temp"}]},
    )

    # 删除（value 为 null）
    response = await async_client.patch(
        f"/api/v1/object/{file_id}/metadata",
        headers=auth_headers,
        json={"patches": [{"key": "custom:to_delete", "value": None}]},
    )
    assert response.status_code == 204

    # 验证已删除
    get_response = await async_client.get(
        f"/api/v1/object/{file_id}/metadata?ns=custom",
        headers=auth_headers,
    )
    data = get_response.json()
    assert "custom:to_delete" not in data["metadatas"]


@pytest.mark.asyncio
async def test_patch_metadata_reject_non_custom_namespace(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID],
):
    """测试拒绝修改非 custom: 命名空间"""
    file_id = test_directory_structure["file_id"]

    response = await async_client.patch(
        f"/api/v1/object/{file_id}/metadata",
        headers=auth_headers,
        json={"patches": [{"key": "exif:width", "value": "1920"}]},
    )
    assert response.status_code == 400
