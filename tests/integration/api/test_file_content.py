"""
文本文件内容 GET/PATCH 集成测试

测试 GET /file/content/{file_id} 和 PATCH /file/content/{file_id} 端点。
"""
import hashlib
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodels import Entry, EntryType, PhysicalFile, Policy, User


# ==================== Fixtures ====================

@pytest_asyncio.fixture
async def local_policy(
    initialized_db: AsyncSession,
    tmp_path: Path,
) -> Policy:
    """创建指向临时目录的本地存储策略"""
    from sqlmodels import PolicyType

    policy = Policy(
        id=uuid4(),
        name="测试本地存储",
        type=PolicyType.LOCAL,
        server=str(tmp_path),
    )
    initialized_db.add(policy)
    await initialized_db.commit()
    await initialized_db.refresh(policy)
    return policy


@pytest_asyncio.fixture
async def text_file(
    initialized_db: AsyncSession,
    tmp_path: Path,
    local_policy: Policy,
) -> dict[str, str | int]:
    """创建包含 UTF-8 文本内容的测试文件"""
    user = await User.get(initialized_db, User.email == "testuser@example.com")
    root = await Entry.get_root(initialized_db, user.id)

    content = "line1\nline2\nline3\n"
    content_bytes = content.encode('utf-8')
    content_hash = hashlib.sha256(content_bytes).hexdigest()

    file_path = tmp_path / "test.txt"
    file_path.write_bytes(content_bytes)

    physical_file = PhysicalFile(
        id=uuid4(),
        storage_path=str(file_path),
        size=len(content_bytes),
        policy_id=local_policy.id,
        reference_count=1,
    )
    initialized_db.add(physical_file)

    file_obj = Entry(
        id=uuid4(),
        name="test.txt",
        type=EntryType.FILE,
        size=len(content_bytes),
        physical_file_id=physical_file.id,
        parent_id=root.id,
        owner_id=user.id,
        policy_id=local_policy.id,
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


@pytest_asyncio.fixture
async def binary_file(
    initialized_db: AsyncSession,
    tmp_path: Path,
    local_policy: Policy,
) -> dict[str, str | int]:
    """创建非 UTF-8 的二进制测试文件"""
    user = await User.get(initialized_db, User.email == "testuser@example.com")
    root = await Entry.get_root(initialized_db, user.id)

    # 包含无效 UTF-8 字节序列
    content_bytes = b'\x80\x81\x82\xff\xfe\xfd'

    file_path = tmp_path / "binary.dat"
    file_path.write_bytes(content_bytes)

    physical_file = PhysicalFile(
        id=uuid4(),
        storage_path=str(file_path),
        size=len(content_bytes),
        policy_id=local_policy.id,
        reference_count=1,
    )
    initialized_db.add(physical_file)

    file_obj = Entry(
        id=uuid4(),
        name="binary.dat",
        type=EntryType.FILE,
        size=len(content_bytes),
        physical_file_id=physical_file.id,
        parent_id=root.id,
        owner_id=user.id,
        policy_id=local_policy.id,
    )
    initialized_db.add(file_obj)
    await initialized_db.commit()

    return {
        "id": str(file_obj.id),
        "path": str(file_path),
    }


# ==================== GET /file/content/{file_id} ====================

class TestGetFileContent:
    """GET /file/content/{file_id} 端点测试"""

    @pytest.mark.asyncio
    async def test_get_content_success(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        text_file: dict[str, str | int],
    ) -> None:
        """成功获取文本文件内容和哈希"""
        response = await async_client.get(
            f"/api/v1/file/content/{text_file['id']}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["content"] == text_file["content"]
        assert data["hash"] == text_file["hash"]
        assert data["size"] == text_file["size"]

    @pytest.mark.asyncio
    async def test_get_content_non_utf8_returns_400(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        binary_file: dict[str, str | int],
    ) -> None:
        """非 UTF-8 文件返回 400"""
        response = await async_client.get(
            f"/api/v1/file/content/{binary_file['id']}",
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "UTF-8" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_content_not_found(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """文件不存在返回 404"""
        fake_id = uuid4()
        response = await async_client.get(
            f"/api/v1/file/content/{fake_id}",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_content_unauthenticated(
        self,
        async_client: AsyncClient,
        text_file: dict[str, str | int],
    ) -> None:
        """未认证返回 401"""
        response = await async_client.get(
            f"/api/v1/file/content/{text_file['id']}",
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_content_normalizes_crlf(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        initialized_db: AsyncSession,
        tmp_path: Path,
        local_policy: Policy,
    ) -> None:
        """CRLF 换行符被规范化为 LF"""
        user = await User.get(initialized_db, User.email == "testuser@example.com")
        root = await Entry.get_root(initialized_db, user.id)

        crlf_content = b"line1\r\nline2\r\n"
        file_path = tmp_path / "crlf.txt"
        file_path.write_bytes(crlf_content)

        physical_file = PhysicalFile(
            id=uuid4(),
            storage_path=str(file_path),
            size=len(crlf_content),
            policy_id=local_policy.id,
            reference_count=1,
        )
        initialized_db.add(physical_file)

        file_obj = Entry(
            id=uuid4(),
            name="crlf.txt",
            type=EntryType.FILE,
            size=len(crlf_content),
            physical_file_id=physical_file.id,
            parent_id=root.id,
            owner_id=user.id,
            policy_id=local_policy.id,
        )
        initialized_db.add(file_obj)
        await initialized_db.commit()

        response = await async_client.get(
            f"/api/v1/file/content/{file_obj.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        # 内容应该被规范化为 LF
        assert data["content"] == "line1\nline2\n"
        # 哈希基于规范化后的内容
        expected_hash = hashlib.sha256("line1\nline2\n".encode('utf-8')).hexdigest()
        assert data["hash"] == expected_hash


# ==================== PATCH /file/content/{file_id} ====================

class TestPatchFileContent:
    """PATCH /file/content/{file_id} 端点测试"""

    @pytest.mark.asyncio
    async def test_patch_content_success(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        text_file: dict[str, str | int],
    ) -> None:
        """正常增量保存"""
        patch_text = (
            "--- a\n"
            "+++ b\n"
            "@@ -1,3 +1,3 @@\n"
            " line1\n"
            "-line2\n"
            "+LINE2_MODIFIED\n"
            " line3\n"
        )

        response = await async_client.patch(
            f"/api/v1/file/content/{text_file['id']}",
            headers=auth_headers,
            json={
                "patch": patch_text,
                "base_hash": text_file["hash"],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "new_hash" in data
        assert "new_size" in data
        assert data["new_hash"] != text_file["hash"]

        # 验证文件实际被修改
        file_path = Path(text_file["path"])
        new_content = file_path.read_text(encoding='utf-8')
        assert "LINE2_MODIFIED" in new_content
        assert "line2" not in new_content

    @pytest.mark.asyncio
    async def test_patch_content_hash_mismatch_returns_409(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        text_file: dict[str, str | int],
    ) -> None:
        """base_hash 不匹配返回 409"""
        patch_text = (
            "--- a\n"
            "+++ b\n"
            "@@ -1,3 +1,3 @@\n"
            " line1\n"
            "-line2\n"
            "+changed\n"
            " line3\n"
        )

        response = await async_client.patch(
            f"/api/v1/file/content/{text_file['id']}",
            headers=auth_headers,
            json={
                "patch": patch_text,
                "base_hash": "0" * 64,  # 错误的哈希
            },
        )

        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_patch_content_invalid_patch_returns_422(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        text_file: dict[str, str | int],
    ) -> None:
        """无效的 patch 格式返回 422"""
        response = await async_client.patch(
            f"/api/v1/file/content/{text_file['id']}",
            headers=auth_headers,
            json={
                "patch": "this is not a valid patch",
                "base_hash": text_file["hash"],
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_content_context_mismatch_returns_422(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        text_file: dict[str, str | int],
    ) -> None:
        """patch 上下文行不匹配返回 422"""
        patch_text = (
            "--- a\n"
            "+++ b\n"
            "@@ -1,3 +1,3 @@\n"
            " WRONG_CONTEXT_LINE\n"
            "-line2\n"
            "+replaced\n"
            " line3\n"
        )

        response = await async_client.patch(
            f"/api/v1/file/content/{text_file['id']}",
            headers=auth_headers,
            json={
                "patch": patch_text,
                "base_hash": text_file["hash"],
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_content_unauthenticated(
        self,
        async_client: AsyncClient,
        text_file: dict[str, str | int],
    ) -> None:
        """未认证返回 401"""
        response = await async_client.patch(
            f"/api/v1/file/content/{text_file['id']}",
            json={
                "patch": "--- a\n+++ b\n",
                "base_hash": text_file["hash"],
            },
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_patch_content_not_found(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """文件不存在返回 404"""
        fake_id = uuid4()
        response = await async_client.patch(
            f"/api/v1/file/content/{fake_id}",
            headers=auth_headers,
            json={
                "patch": "--- a\n+++ b\n",
                "base_hash": "0" * 64,
            },
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_then_get_consistency(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        text_file: dict[str, str | int],
    ) -> None:
        """PATCH 后 GET 返回一致的内容和哈希"""
        patch_text = (
            "--- a\n"
            "+++ b\n"
            "@@ -1,3 +1,3 @@\n"
            " line1\n"
            "-line2\n"
            "+PATCHED\n"
            " line3\n"
        )

        # PATCH
        patch_resp = await async_client.patch(
            f"/api/v1/file/content/{text_file['id']}",
            headers=auth_headers,
            json={
                "patch": patch_text,
                "base_hash": text_file["hash"],
            },
        )
        assert patch_resp.status_code == 200
        patch_data = patch_resp.json()

        # GET
        get_resp = await async_client.get(
            f"/api/v1/file/content/{text_file['id']}",
            headers=auth_headers,
        )
        assert get_resp.status_code == 200
        get_data = get_resp.json()

        # 一致性验证
        assert get_data["hash"] == patch_data["new_hash"]
        assert get_data["size"] == patch_data["new_size"]
        assert "PATCHED" in get_data["content"]
