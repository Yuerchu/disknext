"""
文件查看器集成测试

测试查看器查询、用户默认设置、用户组过滤等端点。
"""
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodels.file_app import (
    FileApp,
    FileAppExtension,
    FileAppGroupLink,
    FileAppType,
    UserFileAppDefault,
)
from sqlmodels.user import User


# ==================== Fixtures ====================

@pytest_asyncio.fixture
async def setup_file_apps(
    initialized_db: AsyncSession,
) -> dict[str, UUID]:
    """创建测试用文件查看器应用"""
    # PDF 阅读器（不限制用户组）
    pdf_app = FileApp(
        name="PDF 阅读器",
        app_key="pdfjs",
        type=FileAppType.BUILTIN,
        is_enabled=True,
        is_restricted=False,
    )
    pdf_app = await pdf_app.save(initialized_db)

    # Monaco 编辑器（不限制用户组）
    monaco_app = FileApp(
        name="代码编辑器",
        app_key="monaco",
        type=FileAppType.BUILTIN,
        is_enabled=True,
        is_restricted=False,
    )
    monaco_app = await monaco_app.save(initialized_db)

    # Collabora（限制用户组）
    collabora_app = FileApp(
        name="Collabora",
        app_key="collabora",
        type=FileAppType.WOPI,
        is_enabled=True,
        is_restricted=True,
    )
    collabora_app = await collabora_app.save(initialized_db)

    # 已禁用的应用
    disabled_app = FileApp(
        name="禁用的应用",
        app_key="disabled_app",
        type=FileAppType.BUILTIN,
        is_enabled=False,
        is_restricted=False,
    )
    disabled_app = await disabled_app.save(initialized_db)

    # 创建扩展名
    for ext in ["pdf"]:
        await FileAppExtension(app_id=pdf_app.id, extension=ext, priority=0).save(initialized_db)

    for ext in ["txt", "md", "json"]:
        await FileAppExtension(app_id=monaco_app.id, extension=ext, priority=0).save(initialized_db)

    for ext in ["docx", "xlsx", "pptx"]:
        await FileAppExtension(app_id=collabora_app.id, extension=ext, priority=0).save(initialized_db)

    for ext in ["pdf"]:
        await FileAppExtension(app_id=disabled_app.id, extension=ext, priority=10).save(initialized_db)

    return {
        "pdf_app_id": pdf_app.id,
        "monaco_app_id": monaco_app.id,
        "collabora_app_id": collabora_app.id,
        "disabled_app_id": disabled_app.id,
    }


# ==================== GET /file/viewers ====================

class TestGetViewers:
    """查询可用查看器测试"""

    @pytest.mark.asyncio
    async def test_get_viewers_for_pdf(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        setup_file_apps: dict[str, UUID],
    ) -> None:
        """查询 PDF 查看器：返回已启用的，排除已禁用的"""
        response = await async_client.get(
            "/api/v1/file/viewers?ext=pdf",
            headers=auth_headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert "viewers" in data
        viewer_keys = [v["app_key"] for v in data["viewers"]]

        # pdfjs 应该在列表中
        assert "pdfjs" in viewer_keys
        # 禁用的应用不应出现
        assert "disabled_app" not in viewer_keys
        # 默认值应为 None
        assert data["default_viewer_id"] is None

    @pytest.mark.asyncio
    async def test_get_viewers_normalizes_extension(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        setup_file_apps: dict[str, UUID],
    ) -> None:
        """扩展名规范化：.PDF → pdf"""
        response = await async_client.get(
            "/api/v1/file/viewers?ext=.PDF",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["viewers"]) >= 1

    @pytest.mark.asyncio
    async def test_get_viewers_empty_for_unknown_ext(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        setup_file_apps: dict[str, UUID],
    ) -> None:
        """未知扩展名返回空列表"""
        response = await async_client.get(
            "/api/v1/file/viewers?ext=xyz_unknown",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["viewers"] == []

    @pytest.mark.asyncio
    async def test_group_restriction_filters_app(
        self,
        async_client: AsyncClient,
        initialized_db: AsyncSession,
        auth_headers: dict[str, str],
        setup_file_apps: dict[str, UUID],
    ) -> None:
        """用户组限制：collabora 限制了用户组，用户不在白名单内则不可见"""
        # collabora 是受限的，用户组不在白名单中
        response = await async_client.get(
            "/api/v1/file/viewers?ext=docx",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        viewer_keys = [v["app_key"] for v in data["viewers"]]
        assert "collabora" not in viewer_keys

        # 将用户组加入白名单
        test_user = await User.get(initialized_db, User.email == "testuser@example.com")
        link = FileAppGroupLink(
            app_id=setup_file_apps["collabora_app_id"],
            group_id=test_user.group_id,
        )
        initialized_db.add(link)
        await initialized_db.commit()

        # 再次查询
        response = await async_client.get(
            "/api/v1/file/viewers?ext=docx",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        viewer_keys = [v["app_key"] for v in data["viewers"]]
        assert "collabora" in viewer_keys

    @pytest.mark.asyncio
    async def test_unauthorized_without_token(
        self,
        async_client: AsyncClient,
    ) -> None:
        """未认证请求返回 401"""
        response = await async_client.get("/api/v1/file/viewers?ext=pdf")
        assert response.status_code in (401, 403)


# ==================== User File Viewer Defaults ====================

class TestUserFileViewerDefaults:
    """用户默认查看器设置测试"""

    @pytest.mark.asyncio
    async def test_set_default_viewer(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        setup_file_apps: dict[str, UUID],
    ) -> None:
        """设置默认查看器"""
        response = await async_client.put(
            "/api/v1/user/settings/file_viewers/default",
            headers=auth_headers,
            json={
                "extension": "pdf",
                "app_id": str(setup_file_apps["pdf_app_id"]),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["extension"] == "pdf"
        assert data["app"]["app_key"] == "pdfjs"

    @pytest.mark.asyncio
    async def test_list_default_viewers(
        self,
        async_client: AsyncClient,
        initialized_db: AsyncSession,
        auth_headers: dict[str, str],
        setup_file_apps: dict[str, UUID],
    ) -> None:
        """列出默认查看器"""
        # 先创建一个默认
        test_user = await User.get(initialized_db, User.email == "testuser@example.com")
        await UserFileAppDefault(
            user_id=test_user.id,
            extension="pdf",
            app_id=setup_file_apps["pdf_app_id"],
        ).save(initialized_db)

        response = await async_client.get(
            "/api/v1/user/settings/file_viewers/defaults",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_delete_default_viewer(
        self,
        async_client: AsyncClient,
        initialized_db: AsyncSession,
        auth_headers: dict[str, str],
        setup_file_apps: dict[str, UUID],
    ) -> None:
        """撤销默认查看器"""
        # 创建一个默认
        test_user = await User.get(initialized_db, User.email == "testuser@example.com")
        default = await UserFileAppDefault(
            user_id=test_user.id,
            extension="txt",
            app_id=setup_file_apps["monaco_app_id"],
        ).save(initialized_db)

        response = await async_client.delete(
            f"/api/v1/user/settings/file_viewers/default/{default.id}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        # 验证已删除
        found = await UserFileAppDefault.get(
            initialized_db, UserFileAppDefault.id == default.id
        )
        assert found is None

    @pytest.mark.asyncio
    async def test_get_viewers_includes_default(
        self,
        async_client: AsyncClient,
        initialized_db: AsyncSession,
        auth_headers: dict[str, str],
        setup_file_apps: dict[str, UUID],
    ) -> None:
        """查看器查询应包含用户默认选择"""
        # 设置默认
        test_user = await User.get(initialized_db, User.email == "testuser@example.com")
        await UserFileAppDefault(
            user_id=test_user.id,
            extension="pdf",
            app_id=setup_file_apps["pdf_app_id"],
        ).save(initialized_db)

        response = await async_client.get(
            "/api/v1/file/viewers?ext=pdf",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["default_viewer_id"] == str(setup_file_apps["pdf_app_id"])
