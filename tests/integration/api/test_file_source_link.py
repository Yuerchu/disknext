"""
文件外链与 Policy 规则集成测试

测试端点：
- POST /file/source/{file_id}     创建/获取文件外链
- GET  /file/get/{file_id}/{name}  外链直接输出
- GET  /file/source/{file_id}/{name}  外链重定向/输出

测试 Policy 规则：
- max_size 在 PATCH /file/content 中的检查
- is_origin_link_enable 控制外链创建与访问
- is_private + base_url 控制 302 重定向 vs 应用代理
"""
import hashlib
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodels import Entry, EntryType, PhysicalFile, Policy, PolicyType, SourceLink, User


# ==================== Fixtures ====================

@pytest_asyncio.fixture
async def source_policy(
    initialized_db: AsyncSession,
    tmp_path: Path,
) -> Policy:
    """创建启用外链的本地存储策略"""
    policy = Policy(
        id=uuid4(),
        name="测试外链存储",
        type=PolicyType.LOCAL,
        server=str(tmp_path),
        is_origin_link_enable=True,
        is_private=True,
        max_size=0,
    )
    initialized_db.add(policy)
    await initialized_db.commit()
    await initialized_db.refresh(policy)
    return policy


@pytest_asyncio.fixture
async def source_file(
    initialized_db: AsyncSession,
    tmp_path: Path,
    source_policy: Policy,
) -> dict[str, str | int]:
    """创建一个文本测试文件，关联到启用外链的存储策略"""
    user = await User.get(initialized_db, User.email == "testuser@example.com")
    root = await Entry.get_root(initialized_db, user.id)

    content = "A" * 50
    content_bytes = content.encode('utf-8')
    content_hash = hashlib.sha256(content_bytes).hexdigest()

    file_path = tmp_path / "source_test.txt"
    file_path.write_bytes(content_bytes)

    physical_file = PhysicalFile(
        id=uuid4(),
        storage_path=str(file_path),
        size=len(content_bytes),
        policy_id=source_policy.id,
        reference_count=1,
    )
    initialized_db.add(physical_file)

    file_obj = Entry(
        id=uuid4(),
        name="source_test.txt",
        type=EntryType.FILE,
        size=len(content_bytes),
        physical_file_id=physical_file.id,
        parent_id=root.id,
        owner_id=user.id,
        policy_id=source_policy.id,
    )
    initialized_db.add(file_obj)
    await initialized_db.commit()

    return {
        "id": str(file_obj.id),
        "name": "source_test.txt",
        "content": content,
        "hash": content_hash,
        "size": len(content_bytes),
        "path": str(file_path),
    }


@pytest_asyncio.fixture
async def source_file_with_link(
    initialized_db: AsyncSession,
    source_file: dict[str, str | int],
) -> dict[str, str | int]:
    """创建已有 SourceLink 的测试文件"""
    link = SourceLink(
        name=source_file["name"],
        file_id=UUID(source_file["id"]),
        downloads=5,
    )
    initialized_db.add(link)
    await initialized_db.commit()
    await initialized_db.refresh(link)

    return {**source_file, "link_id": link.id, "link_downloads": 5}


# ==================== POST /file/source/{file_id} ====================

class TestCreateSourceLink:
    """POST /file/source/{file_id} 端点测试"""

    @pytest.mark.asyncio
    async def test_create_source_link_success(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        source_file: dict[str, str | int],
    ) -> None:
        """成功创建外链"""
        response = await async_client.post(
            f"/api/v1/file/source/{source_file['id']}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "/api/v1/file/source/" in data["url"]
        assert source_file["name"] in data["url"]
        assert data["downloads"] == 0

    @pytest.mark.asyncio
    async def test_create_source_link_idempotent(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        source_file_with_link: dict[str, str | int],
    ) -> None:
        """已有外链时返回现有外链（幂等）"""
        response = await async_client.post(
            f"/api/v1/file/source/{source_file_with_link['id']}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["downloads"] == source_file_with_link["link_downloads"]

    @pytest.mark.asyncio
    async def test_create_source_link_disabled_returns_403(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        source_file: dict[str, str | int],
        source_policy: Policy,
        initialized_db: AsyncSession,
    ) -> None:
        """存储策略未启用外链时返回 403"""
        source_policy.is_origin_link_enable = False
        initialized_db.add(source_policy)
        await initialized_db.commit()

        response = await async_client.post(
            f"/api/v1/file/source/{source_file['id']}",
            headers=auth_headers,
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_source_link_file_not_found(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """文件不存在返回 404"""
        response = await async_client.post(
            f"/api/v1/file/source/{uuid4()}",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_source_link_unauthenticated(
        self,
        async_client: AsyncClient,
        source_file: dict[str, str | int],
    ) -> None:
        """未认证返回 401"""
        response = await async_client.post(
            f"/api/v1/file/source/{source_file['id']}",
        )

        assert response.status_code == 401


# ==================== GET /file/get/{file_id}/{name} ====================

class TestFileGetDirect:
    """GET /file/get/{file_id}/{name} 端点测试"""

    @pytest.mark.asyncio
    async def test_get_direct_success(
        self,
        async_client: AsyncClient,
        source_file_with_link: dict[str, str | int],
    ) -> None:
        """成功通过外链直接获取文件（无需认证）"""
        response = await async_client.get(
            f"/api/v1/file/get/{source_file_with_link['id']}/{source_file_with_link['name']}",
        )

        assert response.status_code == 200
        assert source_file_with_link["content"] in response.text

    @pytest.mark.asyncio
    async def test_get_direct_increments_download_count(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        source_file_with_link: dict[str, str | int],
        initialized_db: AsyncSession,
    ) -> None:
        """下载后递增计数"""
        link_before = await SourceLink.get(
            initialized_db,
            SourceLink.file_id == UUID(source_file_with_link["id"]),
        )
        downloads_before = link_before.downloads

        await async_client.get(
            f"/api/v1/file/get/{source_file_with_link['id']}/{source_file_with_link['name']}",
        )

        await initialized_db.refresh(link_before)
        assert link_before.downloads == downloads_before + 1

    @pytest.mark.asyncio
    async def test_get_direct_no_link_returns_404(
        self,
        async_client: AsyncClient,
        source_file: dict[str, str | int],
    ) -> None:
        """未创建外链的文件返回 404"""
        response = await async_client.get(
            f"/api/v1/file/get/{source_file['id']}/{source_file['name']}",
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_direct_nonexistent_file_returns_404(
        self,
        async_client: AsyncClient,
    ) -> None:
        """文件不存在返回 404"""
        response = await async_client.get(
            f"/api/v1/file/get/{uuid4()}/fake.txt",
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_direct_disabled_policy_returns_403(
        self,
        async_client: AsyncClient,
        source_file_with_link: dict[str, str | int],
        source_policy: Policy,
        initialized_db: AsyncSession,
    ) -> None:
        """存储策略禁用外链时返回 403"""
        source_policy.is_origin_link_enable = False
        initialized_db.add(source_policy)
        await initialized_db.commit()

        response = await async_client.get(
            f"/api/v1/file/get/{source_file_with_link['id']}/{source_file_with_link['name']}",
        )

        assert response.status_code == 403


# ==================== GET /file/source/{file_id}/{name} ====================

class TestFileSourceRedirect:
    """GET /file/source/{file_id}/{name} 端点测试"""

    @pytest.mark.asyncio
    async def test_source_private_returns_file_content(
        self,
        async_client: AsyncClient,
        source_file_with_link: dict[str, str | int],
    ) -> None:
        """is_private=True 时直接返回文件内容"""
        response = await async_client.get(
            f"/api/v1/file/source/{source_file_with_link['id']}/{source_file_with_link['name']}",
            follow_redirects=False,
        )

        assert response.status_code == 200
        assert source_file_with_link["content"] in response.text

    @pytest.mark.asyncio
    async def test_source_public_redirects_302(
        self,
        async_client: AsyncClient,
        source_file_with_link: dict[str, str | int],
        source_policy: Policy,
        initialized_db: AsyncSession,
    ) -> None:
        """is_private=False + base_url 时 302 重定向"""
        source_policy.is_private = False
        source_policy.base_url = "http://cdn.example.com/storage"
        initialized_db.add(source_policy)
        await initialized_db.commit()

        response = await async_client.get(
            f"/api/v1/file/source/{source_file_with_link['id']}/{source_file_with_link['name']}",
            follow_redirects=False,
        )

        assert response.status_code == 302
        location = response.headers["location"]
        assert "cdn.example.com/storage" in location

    @pytest.mark.asyncio
    async def test_source_public_no_base_url_fallback(
        self,
        async_client: AsyncClient,
        source_file_with_link: dict[str, str | int],
        source_policy: Policy,
        initialized_db: AsyncSession,
    ) -> None:
        """is_private=False 但 base_url 为空时降级为直接输出"""
        source_policy.is_private = False
        source_policy.base_url = None
        initialized_db.add(source_policy)
        await initialized_db.commit()

        response = await async_client.get(
            f"/api/v1/file/source/{source_file_with_link['id']}/{source_file_with_link['name']}",
            follow_redirects=False,
        )

        assert response.status_code == 200
        assert source_file_with_link["content"] in response.text

    @pytest.mark.asyncio
    async def test_source_increments_download_count(
        self,
        async_client: AsyncClient,
        source_file_with_link: dict[str, str | int],
        initialized_db: AsyncSession,
    ) -> None:
        """访问外链递增下载计数"""
        link_before = await SourceLink.get(
            initialized_db,
            SourceLink.file_id == UUID(source_file_with_link["id"]),
        )
        downloads_before = link_before.downloads

        await async_client.get(
            f"/api/v1/file/source/{source_file_with_link['id']}/{source_file_with_link['name']}",
        )

        await initialized_db.refresh(link_before)
        assert link_before.downloads == downloads_before + 1

    @pytest.mark.asyncio
    async def test_source_no_link_returns_404(
        self,
        async_client: AsyncClient,
        source_file: dict[str, str | int],
    ) -> None:
        """未创建外链的文件返回 404"""
        response = await async_client.get(
            f"/api/v1/file/source/{source_file['id']}/{source_file['name']}",
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_source_disabled_policy_returns_403(
        self,
        async_client: AsyncClient,
        source_file_with_link: dict[str, str | int],
        source_policy: Policy,
        initialized_db: AsyncSession,
    ) -> None:
        """存储策略禁用外链时返回 403"""
        source_policy.is_origin_link_enable = False
        initialized_db.add(source_policy)
        await initialized_db.commit()

        response = await async_client.get(
            f"/api/v1/file/source/{source_file_with_link['id']}/{source_file_with_link['name']}",
        )

        assert response.status_code == 403


# ==================== max_size 在 PATCH 中的检查 ====================

class TestPatchMaxSizePolicy:
    """PATCH /file/content/{file_id} 的 max_size 策略检查"""

    @pytest_asyncio.fixture
    async def size_limited_policy(
        self,
        initialized_db: AsyncSession,
        tmp_path: Path,
    ) -> Policy:
        """创建有大小限制的存储策略（100 bytes）"""
        policy = Policy(
            id=uuid4(),
            name="限制大小存储",
            type=PolicyType.LOCAL,
            server=str(tmp_path),
            max_size=100,
        )
        initialized_db.add(policy)
        await initialized_db.commit()
        await initialized_db.refresh(policy)
        return policy

    @pytest_asyncio.fixture
    async def small_file(
        self,
        initialized_db: AsyncSession,
        tmp_path: Path,
        size_limited_policy: Policy,
    ) -> dict[str, str | int]:
        """创建一个 50 字节的文本文件（策略限制 100 字节）"""
        user = await User.get(initialized_db, User.email == "testuser@example.com")
        root = await Entry.get_root(initialized_db, user.id)

        content = "A" * 50
        content_bytes = content.encode('utf-8')
        content_hash = hashlib.sha256(content_bytes).hexdigest()

        file_path = tmp_path / "small.txt"
        file_path.write_bytes(content_bytes)

        physical_file = PhysicalFile(
            id=uuid4(),
            storage_path=str(file_path),
            size=len(content_bytes),
            policy_id=size_limited_policy.id,
            reference_count=1,
        )
        initialized_db.add(physical_file)

        file_obj = Entry(
            id=uuid4(),
            name="small.txt",
            type=EntryType.FILE,
            size=len(content_bytes),
            physical_file_id=physical_file.id,
            parent_id=root.id,
            owner_id=user.id,
            policy_id=size_limited_policy.id,
        )
        initialized_db.add(file_obj)
        await initialized_db.commit()

        return {
            "id": str(file_obj.id),
            "content": content,
            "hash": content_hash,
            "size": len(content_bytes),
            "path": str(file_path),
        }

    @pytest.mark.asyncio
    async def test_patch_exceeds_max_size_returns_413(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        small_file: dict[str, str | int],
    ) -> None:
        """PATCH 后文件超过 max_size 返回 413"""
        big_content = "B" * 200
        patch_text = (
            "--- a\n"
            "+++ b\n"
            "@@ -1 +1 @@\n"
            f"-{'A' * 50}\n"
            f"+{big_content}\n"
        )

        response = await async_client.patch(
            f"/api/v1/file/content/{small_file['id']}",
            headers=auth_headers,
            json={
                "patch": patch_text,
                "base_hash": small_file["hash"],
            },
        )

        assert response.status_code == 413

    @pytest.mark.asyncio
    async def test_patch_within_max_size_succeeds(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        small_file: dict[str, str | int],
    ) -> None:
        """PATCH 后文件未超过 max_size 正常保存"""
        new_content = "C" * 80  # 80 bytes < 100 bytes limit
        patch_text = (
            "--- a\n"
            "+++ b\n"
            "@@ -1 +1 @@\n"
            f"-{'A' * 50}\n"
            f"+{new_content}\n"
        )

        response = await async_client.patch(
            f"/api/v1/file/content/{small_file['id']}",
            headers=auth_headers,
            json={
                "patch": patch_text,
                "base_hash": small_file["hash"],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["new_size"] == 80
