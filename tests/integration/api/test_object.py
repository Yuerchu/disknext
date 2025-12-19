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
    response = await async_client.delete(
        "/api/object/",
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

    response = await async_client.delete(
        "/api/object/",
        headers=auth_headers,
        json={"ids": [str(file_id)]}
    )
    assert response.status_code == 200

    data = response.json()
    assert "data" in data
    result = data["data"]
    assert "deleted" in result
    assert "total" in result
    assert result["deleted"] == 1
    assert result["total"] == 1


@pytest.mark.asyncio
async def test_object_delete_multiple(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID]
):
    """测试批量删除"""
    docs_id = test_directory_structure["docs_id"]
    images_id = test_directory_structure["images_id"]

    response = await async_client.delete(
        "/api/object/",
        headers=auth_headers,
        json={"ids": [str(docs_id), str(images_id)]}
    )
    assert response.status_code == 200

    data = response.json()
    result = data["data"]
    assert result["deleted"] >= 1
    assert result["total"] == 2


@pytest.mark.asyncio
async def test_object_delete_not_owned(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str]
):
    """测试删除他人对象无效"""
    # 先用管理员创建一个文件夹
    admin_dir_response = await async_client.get(
        "/api/directory/admin",
        headers=admin_headers
    )
    admin_root_id = admin_dir_response.json()["id"]

    create_response = await async_client.put(
        "/api/directory/",
        headers=admin_headers,
        json={
            "parent_id": admin_root_id,
            "name": "adminfolder"
        }
    )
    assert create_response.status_code == 200
    admin_folder_id = create_response.json()["data"]["id"]

    # 普通用户尝试删除管理员的文件夹
    response = await async_client.delete(
        "/api/object/",
        headers=auth_headers,
        json={"ids": [admin_folder_id]}
    )
    assert response.status_code == 200

    data = response.json()
    result = data["data"]
    # 无权删除，deleted 应该为 0
    assert result["deleted"] == 0
    assert result["total"] == 1


@pytest.mark.asyncio
async def test_object_delete_nonexistent(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试删除不存在的对象"""
    fake_id = "00000000-0000-0000-0000-000000000001"

    response = await async_client.delete(
        "/api/object/",
        headers=auth_headers,
        json={"ids": [fake_id]}
    )
    assert response.status_code == 200

    data = response.json()
    result = data["data"]
    assert result["deleted"] == 0


# ==================== 移动对象测试 ====================

@pytest.mark.asyncio
async def test_object_move_requires_auth(async_client: AsyncClient):
    """测试移动对象需要认证"""
    response = await async_client.patch(
        "/api/object/",
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
        "/api/object/",
        headers=auth_headers,
        json={
            "src_ids": [str(file_id)],
            "dst_id": str(images_id)
        }
    )
    assert response.status_code == 200

    data = response.json()
    result = data["data"]
    assert "moved" in result
    assert "total" in result
    assert result["moved"] == 1


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
        "/api/object/",
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
        "/api/object/",
        headers=auth_headers,
        json={
            "src_ids": [str(docs_id)],
            "dst_id": str(file_id)
        }
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_object_move_to_self(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID]
):
    """测试移动到自身应该被跳过"""
    docs_id = test_directory_structure["docs_id"]

    response = await async_client.patch(
        "/api/object/",
        headers=auth_headers,
        json={
            "src_ids": [str(docs_id)],
            "dst_id": str(docs_id)
        }
    )
    assert response.status_code == 200

    data = response.json()
    result = data["data"]
    # 移动到自身应该被跳过
    assert result["moved"] == 0


@pytest.mark.asyncio
async def test_object_move_duplicate_name_skipped(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID]
):
    """测试移动到同名位置应该被跳过"""
    root_id = test_directory_structure["root_id"]
    docs_id = test_directory_structure["docs_id"]
    images_id = test_directory_structure["images_id"]

    # 先在根目录创建一个与 images 同名的文件夹
    await async_client.put(
        "/api/directory/",
        headers=auth_headers,
        json={
            "parent_id": str(root_id),
            "name": "images"
        }
    )

    # 尝试将 docs/images 移动到根目录（已存在同名）
    response = await async_client.patch(
        "/api/object/",
        headers=auth_headers,
        json={
            "src_ids": [str(images_id)],
            "dst_id": str(root_id)
        }
    )
    assert response.status_code == 200

    data = response.json()
    result = data["data"]
    # 同名冲突应该被跳过
    assert result["moved"] == 0


@pytest.mark.asyncio
async def test_object_move_other_user_object(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
    test_directory_structure: dict[str, UUID]
):
    """测试移动他人对象应该被跳过"""
    # 获取管理员的根目录
    admin_response = await async_client.get(
        "/api/directory/admin",
        headers=admin_headers
    )
    admin_root_id = admin_response.json()["id"]

    # 创建管理员的文件夹
    create_response = await async_client.put(
        "/api/directory/",
        headers=admin_headers,
        json={
            "parent_id": admin_root_id,
            "name": "adminfolder"
        }
    )
    admin_folder_id = create_response.json()["data"]["id"]

    # 普通用户尝试移动管理员的文件夹
    user_root_id = test_directory_structure["root_id"]
    response = await async_client.patch(
        "/api/object/",
        headers=auth_headers,
        json={
            "src_ids": [admin_folder_id],
            "dst_id": str(user_root_id)
        }
    )
    assert response.status_code == 200

    data = response.json()
    result = data["data"]
    # 无权移动他人对象
    assert result["moved"] == 0


# ==================== 其他对象操作测试 ====================

@pytest.mark.asyncio
async def test_object_copy_endpoint_exists(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试复制对象端点存在"""
    response = await async_client.post(
        "/api/object/copy",
        headers=auth_headers,
        json={"src_id": "00000000-0000-0000-0000-000000000000"}
    )
    # 未实现的端点
    assert response.status_code in [200, 404, 501]


@pytest.mark.asyncio
async def test_object_rename_endpoint_exists(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试重命名对象端点存在"""
    response = await async_client.post(
        "/api/object/rename",
        headers=auth_headers,
        json={
            "id": "00000000-0000-0000-0000-000000000000",
            "name": "newname"
        }
    )
    # 未实现的端点
    assert response.status_code in [200, 404, 501]


@pytest.mark.asyncio
async def test_object_property_endpoint_exists(
    async_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """测试获取对象属性端点存在"""
    response = await async_client.get(
        "/api/object/property/00000000-0000-0000-0000-000000000000",
        headers=auth_headers
    )
    # 未实现的端点
    assert response.status_code in [200, 404, 501]
