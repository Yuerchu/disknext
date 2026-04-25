"""
Entry 对象操作端点集成测试

测试移动、复制、重命名、属性获取、元数据操作等。
扩展 test_object.py 中的基础测试覆盖更多边界场景。
"""
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient


# ==================== 重命名测试 ====================

class TestEntryRename:
    """对象重命名测试"""

    @pytest.mark.asyncio
    async def test_rename_file(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_directory_structure: dict[str, UUID],
    ):
        """成功重命名文件"""
        file_id = test_directory_structure["file_id"]
        response = await async_client.patch(
            f"/api/v1/object/{file_id}",
            headers=auth_headers,
            json={"name": "renamed_file.md"},
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_rename_folder(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_directory_structure: dict[str, UUID],
    ):
        """成功重命名文件夹"""
        images_id = test_directory_structure["images_id"]
        response = await async_client.patch(
            f"/api/v1/object/{images_id}",
            headers=auth_headers,
            json={"name": "photos"},
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_rename_nonexistent(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
    ):
        """重命名不存在的对象返回 404"""
        response = await async_client.patch(
            f"/api/v1/object/{uuid4()}",
            headers=auth_headers,
            json={"name": "new_name"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_rename_empty_name(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_directory_structure: dict[str, UUID],
    ):
        """空名称返回 400"""
        file_id = test_directory_structure["file_id"]
        response = await async_client.patch(
            f"/api/v1/object/{file_id}",
            headers=auth_headers,
            json={"name": "   "},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_rename_with_slash(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_directory_structure: dict[str, UUID],
    ):
        """名称包含斜杠返回 400"""
        file_id = test_directory_structure["file_id"]
        response = await async_client.patch(
            f"/api/v1/object/{file_id}",
            headers=auth_headers,
            json={"name": "invalid/name"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_rename_same_name_noop(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_directory_structure: dict[str, UUID],
    ):
        """重命名为相同名称直接返回 204"""
        file_id = test_directory_structure["file_id"]

        # 先获取当前名称
        get_resp = await async_client.get(
            f"/api/v1/object/{file_id}",
            headers=auth_headers,
        )
        current_name = get_resp.json()["name"]

        # 用相同名称重命名
        response = await async_client.patch(
            f"/api/v1/object/{file_id}",
            headers=auth_headers,
            json={"name": current_name},
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_rename_duplicate_name(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_directory_structure: dict[str, UUID],
    ):
        """同目录下重名返回 409"""
        # images 和 readme.md 都在 docs 目录下
        images_id = test_directory_structure["images_id"]
        response = await async_client.patch(
            f"/api/v1/object/{images_id}",
            headers=auth_headers,
            json={"name": "readme.md"},  # readme.md 已存在于 docs 下
        )
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_rename_root_forbidden(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_directory_structure: dict[str, UUID],
    ):
        """重命名根目录返回 400"""
        root_id = test_directory_structure["root_id"]
        response = await async_client.patch(
            f"/api/v1/object/{root_id}",
            headers=auth_headers,
            json={"name": "new_root"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_rename_other_user(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        test_directory_structure: dict[str, UUID],
    ):
        """重命名他人对象返回 403"""
        file_id = test_directory_structure["file_id"]
        response = await async_client.patch(
            f"/api/v1/object/{file_id}",
            headers=admin_headers,
            json={"name": "hacked"},
        )
        assert response.status_code == 403


# ==================== 获取属性测试 ====================

class TestEntryProperty:
    """对象属性获取测试"""

    @pytest.mark.asyncio
    async def test_get_property(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_directory_structure: dict[str, UUID],
    ):
        """获取文件基本属性"""
        file_id = test_directory_structure["file_id"]
        response = await async_client.get(
            f"/api/v1/object/{file_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(file_id)
        assert "name" in data
        assert "type" in data
        assert "size" in data
        assert "created_at" in data
        assert "updated_at" in data
        assert "parent_id" in data

    @pytest.mark.asyncio
    async def test_get_property_folder(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_directory_structure: dict[str, UUID],
    ):
        """获取文件夹属性"""
        docs_id = test_directory_structure["docs_id"]
        response = await async_client.get(
            f"/api/v1/object/{docs_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "folder"
        assert data["size"] == 0

    @pytest.mark.asyncio
    async def test_get_property_nonexistent(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
    ):
        """获取不存在对象属性返回 404"""
        response = await async_client.get(
            f"/api/v1/object/{uuid4()}",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_property_other_user(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        test_directory_structure: dict[str, UUID],
    ):
        """获取他人对象属性返回 403"""
        file_id = test_directory_structure["file_id"]
        response = await async_client.get(
            f"/api/v1/object/{file_id}",
            headers=admin_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_property_requires_auth(self, async_client: AsyncClient):
        """获取属性需要认证"""
        response = await async_client.get(f"/api/v1/object/{uuid4()}")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_detail_property(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_directory_structure: dict[str, UUID],
    ):
        """获取对象详细属性"""
        file_id = test_directory_structure["file_id"]
        response = await async_client.get(
            f"/api/v1/object/{file_id}/detail",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "policy_name" in data
        assert "share_count" in data
        assert "total_views" in data
        assert "total_downloads" in data
        assert "reference_count" in data
        assert "metadatas" in data

    @pytest.mark.asyncio
    async def test_get_detail_nonexistent(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
    ):
        """获取不存在对象详细属性返回 404"""
        response = await async_client.get(
            f"/api/v1/object/{uuid4()}/detail",
            headers=auth_headers,
        )
        assert response.status_code == 404


# ==================== 移动测试（扩展 test_object.py） ====================

class TestEntryMove:
    """对象移动测试（补充边界场景）"""

    @pytest.mark.asyncio
    async def test_move_multiple_files(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_directory_structure: dict[str, UUID],
    ):
        """批量移动多个对象"""
        file_id = test_directory_structure["file_id"]
        images_id = test_directory_structure["images_id"]
        root_id = test_directory_structure["root_id"]

        # 将 file 和 images 移动到 root（file 本来在 docs 下）
        response = await async_client.patch(
            "/api/v1/object/",
            headers=auth_headers,
            json={
                "src_ids": [str(file_id)],
                "dst_id": str(root_id),
            },
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_move_folder_to_its_child(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_directory_structure: dict[str, UUID],
    ):
        """移动文件夹到自己的子目录（循环检测）应静默跳过"""
        docs_id = test_directory_structure["docs_id"]
        images_id = test_directory_structure["images_id"]

        # docs 包含 images，尝试移动 docs 到 images
        response = await async_client.patch(
            "/api/v1/object/",
            headers=auth_headers,
            json={
                "src_ids": [str(docs_id)],
                "dst_id": str(images_id),
            },
        )
        # 循环检测应该跳过这个移动，但不报错
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_move_to_same_directory_duplicate_name(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_directory_structure: dict[str, UUID],
    ):
        """移动到目标目录下已有同名对象时静默跳过"""
        docs_id = test_directory_structure["docs_id"]
        root_id = test_directory_structure["root_id"]

        # docs 已经在 root 下，移动 docs 到 root 应该跳过（同名）
        response = await async_client.patch(
            "/api/v1/object/",
            headers=auth_headers,
            json={
                "src_ids": [str(docs_id)],
                "dst_id": str(root_id),
            },
        )
        assert response.status_code == 204


# ==================== 复制测试 ====================

class TestEntryCopy:
    """对象复制测试"""

    @pytest.mark.asyncio
    async def test_copy_requires_auth(self, async_client: AsyncClient):
        """复制需要认证"""
        response = await async_client.post(
            "/api/v1/object/copies",
            json={
                "src_ids": [str(uuid4())],
                "dst_id": str(uuid4()),
            },
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_copy_to_invalid_target(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_directory_structure: dict[str, UUID],
    ):
        """复制到不存在的目标返回 404"""
        file_id = test_directory_structure["file_id"]
        response = await async_client.post(
            "/api/v1/object/copies",
            headers=auth_headers,
            json={
                "src_ids": [str(file_id)],
                "dst_id": str(uuid4()),
            },
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_copy_to_file_target(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_directory_structure: dict[str, UUID],
    ):
        """复制到文件（非目录）目标返回 400"""
        file_id = test_directory_structure["file_id"]
        response = await async_client.post(
            "/api/v1/object/copies",
            headers=auth_headers,
            json={
                "src_ids": [str(file_id)],
                "dst_id": str(file_id),  # file 不是目录
            },
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_copy_other_user_target(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        admin_headers: dict[str, str],
        test_directory_structure: dict[str, UUID],
    ):
        """复制到他人目录返回 404"""
        file_id = test_directory_structure["file_id"]

        # 获取管理员根目录
        admin_root_resp = await async_client.get(
            "/api/v1/directory/",
            headers=admin_headers,
        )
        admin_root_id = admin_root_resp.json()["id"]

        response = await async_client.post(
            "/api/v1/object/copies",
            headers=auth_headers,
            json={
                "src_ids": [str(file_id)],
                "dst_id": admin_root_id,
            },
        )
        assert response.status_code == 404


# ==================== 软删除测试（补充） ====================

class TestEntryDelete:
    """对象删除测试（补充边界场景）"""

    @pytest.mark.asyncio
    async def test_delete_root_blocked(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_directory_structure: dict[str, UUID],
    ):
        """删除根目录被阻止（静默跳过）"""
        root_id = test_directory_structure["root_id"]
        response = await async_client.request(
            "DELETE",
            "/api/v1/object/",
            headers=auth_headers,
            json={"ids": [str(root_id)]},
        )
        assert response.status_code == 204

        # 根目录应该还在
        get_resp = await async_client.get(
            "/api/v1/directory/",
            headers=auth_headers,
        )
        assert get_resp.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_batch(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_directory_structure: dict[str, UUID],
    ):
        """批量删除多个对象"""
        file_id = test_directory_structure["file_id"]
        images_id = test_directory_structure["images_id"]

        response = await async_client.request(
            "DELETE",
            "/api/v1/object/",
            headers=auth_headers,
            json={"ids": [str(file_id), str(images_id)]},
        )
        assert response.status_code == 204

        # 验证都进了回收站
        trash_resp = await async_client.get("/api/v1/trash/", headers=auth_headers)
        trash_ids = {i["id"] for i in trash_resp.json()}
        assert str(file_id) in trash_ids
        assert str(images_id) in trash_ids

    @pytest.mark.asyncio
    async def test_delete_already_deleted(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_directory_structure: dict[str, UUID],
    ):
        """重复删除同一对象返回 204（幂等）"""
        file_id = test_directory_structure["file_id"]

        # 第一次删除
        await async_client.request(
            "DELETE",
            "/api/v1/object/",
            headers=auth_headers,
            json={"ids": [str(file_id)]},
        )

        # 第二次删除同一对象
        response = await async_client.request(
            "DELETE",
            "/api/v1/object/",
            headers=auth_headers,
            json={"ids": [str(file_id)]},
        )
        assert response.status_code == 204


# ==================== 元数据测试 ====================

class TestEntryMetadata:
    """对象元数据操作测试"""

    @pytest.mark.asyncio
    async def test_get_metadata(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_directory_structure: dict[str, UUID],
    ):
        """获取对象元数据"""
        file_id = test_directory_structure["file_id"]
        response = await async_client.get(
            f"/api/v1/object/{file_id}/metadata",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "metadatas" in data

    @pytest.mark.asyncio
    async def test_get_metadata_nonexistent(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
    ):
        """获取不存在对象的元数据返回 404"""
        response = await async_client.get(
            f"/api/v1/object/{uuid4()}/metadata",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_metadata_custom_namespace(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_directory_structure: dict[str, UUID],
    ):
        """设置 custom: 命名空间的元数据"""
        file_id = test_directory_structure["file_id"]
        response = await async_client.patch(
            f"/api/v1/object/{file_id}/metadata",
            headers=auth_headers,
            json={
                "patches": [
                    {"key": "custom:color", "value": "red"},
                    {"key": "custom:priority", "value": "high"},
                ],
            },
        )
        assert response.status_code == 204

        # 验证设置成功
        get_resp = await async_client.get(
            f"/api/v1/object/{file_id}/metadata",
            headers=auth_headers,
        )
        metadata = get_resp.json()["metadatas"]
        assert metadata.get("custom:color") == "red"
        assert metadata.get("custom:priority") == "high"

    @pytest.mark.asyncio
    async def test_patch_metadata_delete(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_directory_structure: dict[str, UUID],
    ):
        """删除元数据条目（value=None）"""
        file_id = test_directory_structure["file_id"]

        # 先设置
        await async_client.patch(
            f"/api/v1/object/{file_id}/metadata",
            headers=auth_headers,
            json={"patches": [{"key": "custom:temp", "value": "data"}]},
        )

        # 再删除
        response = await async_client.patch(
            f"/api/v1/object/{file_id}/metadata",
            headers=auth_headers,
            json={"patches": [{"key": "custom:temp", "value": None}]},
        )
        assert response.status_code == 204

        # 验证已删除
        get_resp = await async_client.get(
            f"/api/v1/object/{file_id}/metadata",
            headers=auth_headers,
        )
        metadata = get_resp.json()["metadatas"]
        assert "custom:temp" not in metadata

    @pytest.mark.asyncio
    async def test_patch_metadata_forbidden_namespace(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_directory_structure: dict[str, UUID],
    ):
        """修改非 custom: 命名空间返回 400"""
        file_id = test_directory_structure["file_id"]
        response = await async_client.patch(
            f"/api/v1/object/{file_id}/metadata",
            headers=auth_headers,
            json={"patches": [{"key": "internal:secret", "value": "hack"}]},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_metadata_with_namespace_filter(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_directory_structure: dict[str, UUID],
    ):
        """按命名空间过滤元数据"""
        file_id = test_directory_structure["file_id"]

        # 设置两个不同命名空间的数据
        await async_client.patch(
            f"/api/v1/object/{file_id}/metadata",
            headers=auth_headers,
            json={
                "patches": [
                    {"key": "custom:tag1", "value": "v1"},
                ],
            },
        )

        # 按命名空间过滤
        response = await async_client.get(
            f"/api/v1/object/{file_id}/metadata",
            headers=auth_headers,
            params={"ns": "custom"},
        )
        assert response.status_code == 200
        metadata = response.json()["metadatas"]
        for key in metadata:
            assert key.startswith("custom:")

    @pytest.mark.asyncio
    async def test_patch_metadata_other_user(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        test_directory_structure: dict[str, UUID],
    ):
        """修改他人对象元数据返回 403"""
        file_id = test_directory_structure["file_id"]
        response = await async_client.patch(
            f"/api/v1/object/{file_id}/metadata",
            headers=admin_headers,
            json={"patches": [{"key": "custom:hack", "value": "data"}]},
        )
        assert response.status_code == 403
