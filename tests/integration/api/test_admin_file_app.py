"""
管理员文件应用管理集成测试

测试管理员 CRUD、扩展名更新、用户组权限更新和权限校验。
"""
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodels.file_app import FileApp, FileAppExtension, FileAppType
from sqlmodels.group import Group
from sqlmodels.user import User


# ==================== Fixtures ====================

@pytest_asyncio.fixture
async def setup_admin_app(
    initialized_db: AsyncSession,
) -> dict[str, UUID]:
    """创建测试用管理员文件应用"""
    app = FileApp(
        name="管理员测试应用",
        app_key="admin_test_app",
        type=FileAppType.BUILTIN,
        is_enabled=True,
    )
    app = await app.save(initialized_db)

    ext = FileAppExtension(app_id=app.id, extension="test", priority=0)
    await ext.save(initialized_db)

    return {"app_id": app.id}


# ==================== Admin CRUD ====================

class TestAdminFileAppCRUD:
    """管理员文件应用 CRUD 测试"""

    @pytest.mark.asyncio
    async def test_create_file_app(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
    ) -> None:
        """管理员创建文件应用"""
        response = await async_client.post(
            "/api/v1/admin/file-app/",
            headers=admin_headers,
            json={
                "name": "新建应用",
                "app_key": "new_app",
                "type": "builtin",
                "description": "测试新建",
                "extensions": ["pdf", "txt"],
                "allowed_group_ids": [],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "新建应用"
        assert data["app_key"] == "new_app"
        assert "pdf" in data["extensions"]
        assert "txt" in data["extensions"]

    @pytest.mark.asyncio
    async def test_create_duplicate_app_key(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        setup_admin_app: dict[str, UUID],
    ) -> None:
        """创建重复 app_key 返回 409"""
        response = await async_client.post(
            "/api/v1/admin/file-app/",
            headers=admin_headers,
            json={
                "name": "重复应用",
                "app_key": "admin_test_app",
                "type": "builtin",
            },
        )
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_list_file_apps(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        setup_admin_app: dict[str, UUID],
    ) -> None:
        """管理员列出文件应用"""
        response = await async_client.get(
            "/api/v1/admin/file-app/list",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "apps" in data
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_get_file_app_detail(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        setup_admin_app: dict[str, UUID],
    ) -> None:
        """管理员获取应用详情"""
        app_id = setup_admin_app["app_id"]
        response = await async_client.get(
            f"/api/v1/admin/file-app/{app_id}",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["app_key"] == "admin_test_app"
        assert "test" in data["extensions"]

    @pytest.mark.asyncio
    async def test_get_nonexistent_app(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
    ) -> None:
        """获取不存在的应用返回 404"""
        response = await async_client.get(
            f"/api/v1/admin/file-app/{uuid4()}",
            headers=admin_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_file_app(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        setup_admin_app: dict[str, UUID],
    ) -> None:
        """管理员更新应用"""
        app_id = setup_admin_app["app_id"]
        response = await async_client.patch(
            f"/api/v1/admin/file-app/{app_id}",
            headers=admin_headers,
            json={
                "name": "更新后的名称",
                "is_enabled": False,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "更新后的名称"
        assert data["is_enabled"] is False

    @pytest.mark.asyncio
    async def test_delete_file_app(
        self,
        async_client: AsyncClient,
        initialized_db: AsyncSession,
        admin_headers: dict[str, str],
    ) -> None:
        """管理员删除应用"""
        # 先创建一个应用
        app = FileApp(
            name="待删除应用", app_key="to_delete_admin", type=FileAppType.BUILTIN
        )
        app = await app.save(initialized_db)
        app_id = app.id

        response = await async_client.delete(
            f"/api/v1/admin/file-app/{app_id}",
            headers=admin_headers,
        )
        assert response.status_code == 204

        # 确认已删除
        found = await FileApp.get(initialized_db, FileApp.id == app_id)
        assert found is None


# ==================== Extensions Management ====================

class TestAdminExtensionManagement:
    """管理员扩展名管理测试"""

    @pytest.mark.asyncio
    async def test_update_extensions(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        setup_admin_app: dict[str, UUID],
    ) -> None:
        """全量替换扩展名列表"""
        app_id = setup_admin_app["app_id"]
        response = await async_client.put(
            f"/api/v1/admin/file-app/{app_id}/extensions",
            headers=admin_headers,
            json={"extensions": ["doc", "docx", "odt"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert sorted(data["extensions"]) == ["doc", "docx", "odt"]


# ==================== Group Access Management ====================

class TestAdminGroupAccessManagement:
    """管理员用户组权限管理测试"""

    @pytest.mark.asyncio
    async def test_update_group_access(
        self,
        async_client: AsyncClient,
        initialized_db: AsyncSession,
        admin_headers: dict[str, str],
        setup_admin_app: dict[str, UUID],
    ) -> None:
        """全量替换用户组权限"""
        app_id = setup_admin_app["app_id"]
        admin_user = await User.get(initialized_db, User.email == "admin@disknext.local")
        group_id = admin_user.group_id

        response = await async_client.put(
            f"/api/v1/admin/file-app/{app_id}/groups",
            headers=admin_headers,
            json={"group_ids": [str(group_id)]},
        )
        assert response.status_code == 200
        data = response.json()
        assert str(group_id) in data["allowed_group_ids"]


# ==================== Permission Tests ====================

class TestAdminPermission:
    """权限校验测试"""

    @pytest.mark.asyncio
    async def test_non_admin_forbidden(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """普通用户访问管理端点返回 403"""
        response = await async_client.get(
            "/api/v1/admin/file-app/list",
            headers=auth_headers,
        )
        assert response.status_code == 403
