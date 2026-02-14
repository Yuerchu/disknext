"""
FileApp 模型单元测试

测试 FileApp、FileAppExtension、UserFileAppDefault 的 CRUD 和约束。
"""
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodels.file_app import (
    FileApp,
    FileAppExtension,
    FileAppGroupLink,
    FileAppType,
    UserFileAppDefault,
)
from sqlmodels.group import Group
from sqlmodels.user import User, UserStatus
from sqlmodels.policy import Policy, PolicyType


# ==================== Fixtures ====================

@pytest_asyncio.fixture
async def sample_group(db_session: AsyncSession) -> Group:
    """创建测试用户组"""
    group = Group(name="测试组", max_storage=0, admin=False)
    return await group.save(db_session)


@pytest_asyncio.fixture
async def sample_user(db_session: AsyncSession, sample_group: Group) -> User:
    """创建测试用户"""
    user = User(
        email="fileapp_test@test.local",
        nickname="文件应用测试用户",
        status=UserStatus.ACTIVE,
        group_id=sample_group.id,
    )
    return await user.save(db_session)


@pytest_asyncio.fixture
async def sample_app(db_session: AsyncSession) -> FileApp:
    """创建测试文件应用"""
    app = FileApp(
        name="测试PDF阅读器",
        app_key="test_pdfjs",
        type=FileAppType.BUILTIN,
        icon="file-pdf",
        description="测试用 PDF 阅读器",
        is_enabled=True,
        is_restricted=False,
    )
    return await app.save(db_session)


@pytest_asyncio.fixture
async def sample_app_with_extensions(db_session: AsyncSession, sample_app: FileApp) -> FileApp:
    """创建带扩展名的文件应用"""
    ext1 = FileAppExtension(app_id=sample_app.id, extension="pdf", priority=0)
    ext2 = FileAppExtension(app_id=sample_app.id, extension="djvu", priority=1)
    await ext1.save(db_session)
    await ext2.save(db_session)
    return sample_app


# ==================== FileApp CRUD ====================

class TestFileAppCRUD:
    """FileApp 基础 CRUD 测试"""

    async def test_create_file_app(self, db_session: AsyncSession) -> None:
        """测试创建文件应用"""
        app = FileApp(
            name="Monaco 编辑器",
            app_key="monaco",
            type=FileAppType.BUILTIN,
            description="代码编辑器",
            is_enabled=True,
        )
        app = await app.save(db_session)

        assert app.id is not None
        assert app.name == "Monaco 编辑器"
        assert app.app_key == "monaco"
        assert app.type == FileAppType.BUILTIN
        assert app.is_enabled is True
        assert app.is_restricted is False

    async def test_get_file_app_by_key(self, db_session: AsyncSession, sample_app: FileApp) -> None:
        """测试按 app_key 查询"""
        found = await FileApp.get(db_session, FileApp.app_key == "test_pdfjs")
        assert found is not None
        assert found.id == sample_app.id

    async def test_unique_app_key(self, db_session: AsyncSession, sample_app: FileApp) -> None:
        """测试 app_key 唯一约束"""
        dup = FileApp(
            name="重复应用",
            app_key="test_pdfjs",
            type=FileAppType.BUILTIN,
        )
        with pytest.raises(IntegrityError):
            await dup.save(db_session)

    async def test_update_file_app(self, db_session: AsyncSession, sample_app: FileApp) -> None:
        """测试更新文件应用"""
        sample_app.name = "更新后的名称"
        sample_app.is_enabled = False
        sample_app = await sample_app.save(db_session)

        found = await FileApp.get(db_session, FileApp.id == sample_app.id)
        assert found.name == "更新后的名称"
        assert found.is_enabled is False

    async def test_delete_file_app(self, db_session: AsyncSession) -> None:
        """测试删除文件应用"""
        app = FileApp(
            name="待删除应用",
            app_key="to_delete",
            type=FileAppType.IFRAME,
        )
        app = await app.save(db_session)
        app_id = app.id

        await FileApp.delete(db_session, app)

        found = await FileApp.get(db_session, FileApp.id == app_id)
        assert found is None

    async def test_create_wopi_app(self, db_session: AsyncSession) -> None:
        """测试创建 WOPI 类型应用"""
        app = FileApp(
            name="Collabora",
            app_key="collabora",
            type=FileAppType.WOPI,
            wopi_discovery_url="http://collabora:9980/hosting/discovery",
            wopi_editor_url_template="http://collabora:9980/loleaflet/dist/loleaflet.html?WOPISrc={wopi_src}&access_token={access_token}",
            is_enabled=True,
        )
        app = await app.save(db_session)

        assert app.type == FileAppType.WOPI
        assert app.wopi_discovery_url is not None
        assert app.wopi_editor_url_template is not None

    async def test_create_iframe_app(self, db_session: AsyncSession) -> None:
        """测试创建 iframe 类型应用"""
        app = FileApp(
            name="Office 在线预览",
            app_key="office_viewer",
            type=FileAppType.IFRAME,
            iframe_url_template="https://view.officeapps.live.com/op/embed.aspx?src={file_url}",
            is_enabled=False,
        )
        app = await app.save(db_session)

        assert app.type == FileAppType.IFRAME
        assert "{file_url}" in app.iframe_url_template

    async def test_to_summary(self, db_session: AsyncSession, sample_app: FileApp) -> None:
        """测试转换为摘要 DTO"""
        summary = sample_app.to_summary()
        assert summary.id == sample_app.id
        assert summary.name == sample_app.name
        assert summary.app_key == sample_app.app_key
        assert summary.type == sample_app.type


# ==================== FileAppExtension ====================

class TestFileAppExtension:
    """FileAppExtension 测试"""

    async def test_create_extension(self, db_session: AsyncSession, sample_app: FileApp) -> None:
        """测试创建扩展名关联"""
        ext = FileAppExtension(
            app_id=sample_app.id,
            extension="pdf",
            priority=0,
        )
        ext = await ext.save(db_session)

        assert ext.id is not None
        assert ext.extension == "pdf"
        assert ext.priority == 0

    async def test_query_by_extension(
        self, db_session: AsyncSession, sample_app_with_extensions: FileApp
    ) -> None:
        """测试按扩展名查询"""
        results: list[FileAppExtension] = await FileAppExtension.get(
            db_session,
            FileAppExtension.extension == "pdf",
            fetch_mode="all",
        )
        assert len(results) >= 1
        assert any(r.app_id == sample_app_with_extensions.id for r in results)

    async def test_unique_app_extension(self, db_session: AsyncSession, sample_app: FileApp) -> None:
        """测试 (app_id, extension) 唯一约束"""
        ext1 = FileAppExtension(app_id=sample_app.id, extension="txt", priority=0)
        await ext1.save(db_session)

        ext2 = FileAppExtension(app_id=sample_app.id, extension="txt", priority=1)
        with pytest.raises(IntegrityError):
            await ext2.save(db_session)

    async def test_cascade_delete(
        self, db_session: AsyncSession, sample_app_with_extensions: FileApp
    ) -> None:
        """测试级联删除：删除应用时扩展名也被删除"""
        app_id = sample_app_with_extensions.id

        # 确认扩展名存在
        exts = await FileAppExtension.get(
            db_session,
            FileAppExtension.app_id == app_id,
            fetch_mode="all",
        )
        assert len(exts) == 2

        # 删除应用
        await FileApp.delete(db_session, sample_app_with_extensions)

        # 确认扩展名也被删除
        exts = await FileAppExtension.get(
            db_session,
            FileAppExtension.app_id == app_id,
            fetch_mode="all",
        )
        assert len(exts) == 0


# ==================== FileAppGroupLink ====================

class TestFileAppGroupLink:
    """FileAppGroupLink 用户组访问控制测试"""

    async def test_create_group_link(
        self, db_session: AsyncSession, sample_app: FileApp, sample_group: Group
    ) -> None:
        """测试创建用户组关联"""
        link = FileAppGroupLink(app_id=sample_app.id, group_id=sample_group.id)
        db_session.add(link)
        await db_session.commit()

        result = await db_session.exec(
            select(FileAppGroupLink).where(
                FileAppGroupLink.app_id == sample_app.id,
                FileAppGroupLink.group_id == sample_group.id,
            )
        )
        found = result.first()
        assert found is not None

    async def test_multiple_groups(self, db_session: AsyncSession, sample_app: FileApp) -> None:
        """测试一个应用关联多个用户组"""
        group1 = Group(name="组A", admin=False)
        group1 = await group1.save(db_session)
        group2 = Group(name="组B", admin=False)
        group2 = await group2.save(db_session)

        db_session.add(FileAppGroupLink(app_id=sample_app.id, group_id=group1.id))
        db_session.add(FileAppGroupLink(app_id=sample_app.id, group_id=group2.id))
        await db_session.commit()

        result = await db_session.exec(
            select(FileAppGroupLink).where(FileAppGroupLink.app_id == sample_app.id)
        )
        links = result.all()
        assert len(links) == 2


# ==================== UserFileAppDefault ====================

class TestUserFileAppDefault:
    """UserFileAppDefault 用户偏好测试"""

    async def test_create_default(
        self, db_session: AsyncSession, sample_app: FileApp, sample_user: User
    ) -> None:
        """测试创建用户默认偏好"""
        default = UserFileAppDefault(
            user_id=sample_user.id,
            extension="pdf",
            app_id=sample_app.id,
        )
        default = await default.save(db_session)

        assert default.id is not None
        assert default.extension == "pdf"

    async def test_unique_user_extension(
        self, db_session: AsyncSession, sample_app: FileApp, sample_user: User
    ) -> None:
        """测试 (user_id, extension) 唯一约束"""
        default1 = UserFileAppDefault(
            user_id=sample_user.id, extension="pdf", app_id=sample_app.id
        )
        await default1.save(db_session)

        # 创建另一个应用
        app2 = FileApp(
            name="另一个阅读器",
            app_key="pdf_alt",
            type=FileAppType.BUILTIN,
        )
        app2 = await app2.save(db_session)

        default2 = UserFileAppDefault(
            user_id=sample_user.id, extension="pdf", app_id=app2.id
        )
        with pytest.raises(IntegrityError):
            await default2.save(db_session)

    async def test_cascade_delete_on_app(
        self, db_session: AsyncSession, sample_user: User
    ) -> None:
        """测试级联删除：删除应用时用户偏好也被删除"""
        app = FileApp(
            name="待删除应用2",
            app_key="to_delete_2",
            type=FileAppType.BUILTIN,
        )
        app = await app.save(db_session)
        app_id = app.id

        default = UserFileAppDefault(
            user_id=sample_user.id, extension="xyz", app_id=app_id
        )
        await default.save(db_session)

        # 确认存在
        found = await UserFileAppDefault.get(
            db_session, UserFileAppDefault.app_id == app_id
        )
        assert found is not None

        # 删除应用
        await FileApp.delete(db_session, app)

        # 确认用户偏好也被删除
        found = await UserFileAppDefault.get(
            db_session, UserFileAppDefault.app_id == app_id
        )
        assert found is None


# ==================== DTO ====================

class TestFileAppDTO:
    """DTO 模型测试"""

    async def test_file_app_response_from_app(
        self, db_session: AsyncSession, sample_app_with_extensions: FileApp, sample_group: Group
    ) -> None:
        """测试 FileAppResponse.from_app()"""
        from sqlmodels.file_app import FileAppResponse

        extensions = await FileAppExtension.get(
            db_session,
            FileAppExtension.app_id == sample_app_with_extensions.id,
            fetch_mode="all",
        )

        # 直接构造 link 对象用于 DTO 测试，无需持久化
        link = FileAppGroupLink(
            app_id=sample_app_with_extensions.id,
            group_id=sample_group.id,
        )

        response = FileAppResponse.from_app(
            sample_app_with_extensions, extensions, [link]
        )

        assert response.id == sample_app_with_extensions.id
        assert response.app_key == "test_pdfjs"
        assert "pdf" in response.extensions
        assert "djvu" in response.extensions
        assert sample_group.id in response.allowed_group_ids
