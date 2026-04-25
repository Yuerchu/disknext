"""
文件分类端点集成测试

测试按类别（图片/视频/音频/文档）筛选文件。
"""
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodels.file import Entry, EntryType
from sqlmodels.policy import Policy
from sqlmodels.user import User


# ==================== Fixtures ====================

@pytest.fixture
async def category_files(
    initialized_db: AsyncSession,
    test_directory_structure: dict[str, UUID],
) -> dict[str, UUID]:
    """
    创建不同类型的测试文件用于分类筛选测试。

    在 docs 目录下创建：
    - photo.jpg (图片)
    - video.mp4 (视频)
    - song.mp3 (音频)
    - report.pdf (文档)
    - notes.txt (不属于任何预设分类)
    """
    user = await User.get(initialized_db, User.email == "testuser@example.com")
    policy = await Policy.get(initialized_db, Policy.name == "本地存储")
    parent_id = test_directory_structure["docs_id"]

    files = {}
    test_files = [
        ("photo.jpg", 2048),
        ("screenshot.png", 4096),
        ("video.mp4", 1024 * 1024),
        ("song.mp3", 512 * 1024),
        ("report.pdf", 8192),
        ("document.docx", 4096),
        ("notes.txt", 256),
    ]

    for name, size in test_files:
        entry = Entry(
            name=name,
            type=EntryType.FILE,
            parent_id=parent_id,
            owner_id=user.id,
            policy_id=policy.id,
            size=size,
        )
        entry = await entry.save(initialized_db)
        files[name] = entry.id

    return files


# ==================== 认证测试 ====================

@pytest.mark.asyncio
async def test_category_requires_auth(async_client: AsyncClient):
    """分类筛选需要认证"""
    response = await async_client.get("/api/v1/category/image")
    assert response.status_code == 401


# ==================== 分类查询测试 ====================

@pytest.mark.asyncio
async def test_category_image(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    category_files: dict[str, UUID],
):
    """筛选图片类文件"""
    response = await async_client.get(
        "/api/v1/category/image",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["count"] >= 2  # photo.jpg + screenshot.png

    names = {item["name"] for item in data["items"]}
    assert "photo.jpg" in names
    assert "screenshot.png" in names
    # 非图片文件不应出现
    assert "video.mp4" not in names
    assert "notes.txt" not in names


@pytest.mark.asyncio
async def test_category_video(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    category_files: dict[str, UUID],
):
    """筛选视频类文件"""
    response = await async_client.get(
        "/api/v1/category/video",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["count"] >= 1

    names = {item["name"] for item in data["items"]}
    assert "video.mp4" in names


@pytest.mark.asyncio
async def test_category_audio(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    category_files: dict[str, UUID],
):
    """筛选音频类文件"""
    response = await async_client.get(
        "/api/v1/category/audio",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["count"] >= 1

    names = {item["name"] for item in data["items"]}
    assert "song.mp3" in names


@pytest.mark.asyncio
async def test_category_document(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    category_files: dict[str, UUID],
):
    """筛选文档类文件"""
    response = await async_client.get(
        "/api/v1/category/document",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["count"] >= 1

    names = {item["name"] for item in data["items"]}
    assert "report.pdf" in names


# ==================== 分页测试 ====================

@pytest.mark.asyncio
async def test_category_pagination(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    category_files: dict[str, UUID],
):
    """分页参数生效"""
    response = await async_client.get(
        "/api/v1/category/image",
        headers=auth_headers,
        params={"limit": 1, "offset": 0},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) <= 1
    assert data["count"] >= 2  # 总数不受 limit 影响


# ==================== 无效分类测试 ====================

@pytest.mark.asyncio
async def test_category_invalid(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """无效分类返回 422"""
    response = await async_client.get(
        "/api/v1/category/invalid_category",
        headers=auth_headers,
    )
    assert response.status_code == 422


# ==================== 空结果测试 ====================

@pytest.mark.asyncio
async def test_category_empty_result(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """没有匹配文件时返回空列表"""
    response = await async_client.get(
        "/api/v1/category/video",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert data["items"] == []


# ==================== 只返回文件类型 ====================

@pytest.mark.asyncio
async def test_category_only_files(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    category_files: dict[str, UUID],
):
    """分类结果只包含文件，不包含文件夹"""
    response = await async_client.get(
        "/api/v1/category/image",
        headers=auth_headers,
    )
    assert response.status_code == 200
    for item in response.json()["items"]:
        assert item["type"] == "file"


# ==================== 跨目录搜索 ====================

@pytest.mark.asyncio
async def test_category_cross_directory(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    initialized_db: AsyncSession,
    test_directory_structure: dict[str, UUID],
):
    """分类搜索跨越所有目录"""
    user = await User.get(initialized_db, User.email == "testuser@example.com")
    policy = await Policy.get(initialized_db, Policy.name == "本地存储")

    # 在 docs 下创建一张图片
    docs_img = Entry(
        name="doc_photo.jpg",
        type=EntryType.FILE,
        parent_id=test_directory_structure["docs_id"],
        owner_id=user.id,
        policy_id=policy.id,
        size=1024,
    )
    await docs_img.save(initialized_db)

    # 在 images 下创建另一张图片
    images_img = Entry(
        name="gallery_photo.png",
        type=EntryType.FILE,
        parent_id=test_directory_structure["images_id"],
        owner_id=user.id,
        policy_id=policy.id,
        size=2048,
    )
    await images_img.save(initialized_db)

    # 搜索图片类应该包含两个目录下的文件
    response = await async_client.get(
        "/api/v1/category/image",
        headers=auth_headers,
    )
    assert response.status_code == 200
    names = {item["name"] for item in response.json()["items"]}
    assert "doc_photo.jpg" in names
    assert "gallery_photo.png" in names
