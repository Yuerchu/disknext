"""
回收站端点集成测试

测试回收站的列表、恢复、永久删除和清空功能。
"""
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient


# ==================== 认证测试 ====================

@pytest.mark.asyncio
async def test_trash_list_requires_auth(async_client: AsyncClient):
    """列出回收站需要认证"""
    response = await async_client.get("/api/v1/trash/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_trash_restore_requires_auth(async_client: AsyncClient):
    """恢复对象需要认证"""
    response = await async_client.patch(
        "/api/v1/trash/restore",
        json={"ids": [str(uuid4())]},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_trash_delete_requires_auth(async_client: AsyncClient):
    """永久删除需要认证"""
    response = await async_client.request(
        "DELETE",
        "/api/v1/trash/",
        json={"ids": [str(uuid4())], "is_empty_all": False},
    )
    assert response.status_code == 401


# ==================== 列出回收站 ====================

@pytest.mark.asyncio
async def test_trash_list_empty(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """回收站为空时返回空列表"""
    response = await async_client.get(
        "/api/v1/trash/",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_trash_list_after_delete(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID],
):
    """删除文件后出现在回收站"""
    file_id = test_directory_structure["file_id"]

    # 软删除文件
    delete_resp = await async_client.request(
        "DELETE",
        "/api/v1/object/",
        headers=auth_headers,
        json={"ids": [str(file_id)]},
    )
    assert delete_resp.status_code == 204

    # 检查回收站
    trash_resp = await async_client.get(
        "/api/v1/trash/",
        headers=auth_headers,
    )
    assert trash_resp.status_code == 200
    items = trash_resp.json()
    assert len(items) >= 1

    item = items[0]
    assert "id" in item
    assert "name" in item
    assert "type" in item
    assert "size" in item
    assert "deleted_at" in item
    assert "original_parent_id" in item


@pytest.mark.asyncio
async def test_trash_list_only_top_level(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID],
):
    """回收站只显示顶层删除的对象（不含子对象）"""
    docs_id = test_directory_structure["docs_id"]

    # 删除 docs 目录（包含子目录和文件）
    await async_client.request(
        "DELETE",
        "/api/v1/object/",
        headers=auth_headers,
        json={"ids": [str(docs_id)]},
    )

    # 回收站应该只有 docs，不包含其子对象
    trash_resp = await async_client.get(
        "/api/v1/trash/",
        headers=auth_headers,
    )
    items = trash_resp.json()
    # docs 是顶层删除对象，其子对象不应该出现
    docs_items = [i for i in items if i["name"] == "docs"]
    assert len(docs_items) == 1


# ==================== 恢复对象 ====================

@pytest.mark.asyncio
async def test_trash_restore_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID],
):
    """成功从回收站恢复对象"""
    file_id = test_directory_structure["file_id"]

    # 软删除
    await async_client.request(
        "DELETE",
        "/api/v1/object/",
        headers=auth_headers,
        json={"ids": [str(file_id)]},
    )

    # 恢复
    restore_resp = await async_client.patch(
        "/api/v1/trash/restore",
        headers=auth_headers,
        json={"ids": [str(file_id)]},
    )
    assert restore_resp.status_code == 204

    # 验证回收站为空
    trash_resp = await async_client.get(
        "/api/v1/trash/",
        headers=auth_headers,
    )
    items = trash_resp.json()
    restored_items = [i for i in items if str(i["id"]) == str(file_id)]
    assert len(restored_items) == 0


@pytest.mark.asyncio
async def test_trash_restore_nonexistent(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """恢复不存在的对象返回 204（幂等）"""
    response = await async_client.patch(
        "/api/v1/trash/restore",
        headers=auth_headers,
        json={"ids": [str(uuid4())]},
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_trash_restore_multiple(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID],
):
    """批量恢复多个对象"""
    images_id = test_directory_structure["images_id"]
    docs_id = test_directory_structure["docs_id"]

    # 删除两个目录
    await async_client.request(
        "DELETE",
        "/api/v1/object/",
        headers=auth_headers,
        json={"ids": [str(images_id), str(docs_id)]},
    )

    # 批量恢复
    restore_resp = await async_client.patch(
        "/api/v1/trash/restore",
        headers=auth_headers,
        json={"ids": [str(images_id), str(docs_id)]},
    )
    assert restore_resp.status_code == 204

    # 验证回收站为空
    trash_resp = await async_client.get("/api/v1/trash/", headers=auth_headers)
    assert len(trash_resp.json()) == 0


# ==================== 永久删除 ====================

@pytest.mark.asyncio
async def test_trash_permanent_delete(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID],
):
    """永久删除回收站中的对象"""
    file_id = test_directory_structure["file_id"]

    # 先软删除
    await async_client.request(
        "DELETE",
        "/api/v1/object/",
        headers=auth_headers,
        json={"ids": [str(file_id)]},
    )

    # 永久删除
    perm_delete_resp = await async_client.request(
        "DELETE",
        "/api/v1/trash/",
        headers=auth_headers,
        json={"ids": [str(file_id)], "is_empty_all": False},
    )
    assert perm_delete_resp.status_code == 204

    # 验证回收站为空
    trash_resp = await async_client.get("/api/v1/trash/", headers=auth_headers)
    assert len(trash_resp.json()) == 0


@pytest.mark.asyncio
async def test_trash_permanent_delete_nonexistent(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """永久删除不存在的对象返回 204（幂等）"""
    response = await async_client.request(
        "DELETE",
        "/api/v1/trash/",
        headers=auth_headers,
        json={"ids": [str(uuid4())], "is_empty_all": False},
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_trash_empty_all(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID],
):
    """清空整个回收站"""
    # 删除多个对象到回收站
    file_id = test_directory_structure["file_id"]
    images_id = test_directory_structure["images_id"]
    await async_client.request(
        "DELETE",
        "/api/v1/object/",
        headers=auth_headers,
        json={"ids": [str(file_id), str(images_id)]},
    )

    # 清空回收站
    empty_resp = await async_client.request(
        "DELETE",
        "/api/v1/trash/",
        headers=auth_headers,
        json={"ids": [], "is_empty_all": True},
    )
    assert empty_resp.status_code == 204

    # 验证回收站为空
    trash_resp = await async_client.get("/api/v1/trash/", headers=auth_headers)
    assert trash_resp.json() == []


@pytest.mark.asyncio
async def test_trash_empty_all_already_empty(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """清空已经为空的回收站返回 204"""
    response = await async_client.request(
        "DELETE",
        "/api/v1/trash/",
        headers=auth_headers,
        json={"ids": [], "is_empty_all": True},
    )
    assert response.status_code == 204


# ==================== 删除后恢复完整流程 ====================

@pytest.mark.asyncio
async def test_trash_delete_restore_roundtrip(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID],
):
    """完整的删除→回收站→恢复流程"""
    file_id = test_directory_structure["file_id"]

    # 1. 确认文件存在
    get_resp = await async_client.get(
        f"/api/v1/object/{file_id}",
        headers=auth_headers,
    )
    assert get_resp.status_code == 200

    # 2. 软删除
    await async_client.request(
        "DELETE",
        "/api/v1/object/",
        headers=auth_headers,
        json={"ids": [str(file_id)]},
    )

    # 3. 确认无法通过正常接口访问
    get_resp = await async_client.get(
        f"/api/v1/object/{file_id}",
        headers=auth_headers,
    )
    assert get_resp.status_code == 404

    # 4. 确认在回收站中
    trash_resp = await async_client.get("/api/v1/trash/", headers=auth_headers)
    trash_ids = [i["id"] for i in trash_resp.json()]
    assert str(file_id) in trash_ids

    # 5. 恢复
    await async_client.patch(
        "/api/v1/trash/restore",
        headers=auth_headers,
        json={"ids": [str(file_id)]},
    )

    # 6. 确认文件恢复可访问
    get_resp = await async_client.get(
        f"/api/v1/object/{file_id}",
        headers=auth_headers,
    )
    assert get_resp.status_code == 200
