"""
分享端点集成测试

测试分享的创建、列表、获取、删除，以及密码验证和过期检查。
"""
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodels.file import Entry, EntryType
from sqlmodels.policy import Policy
from sqlmodels.share import Share
from sqlmodels.user import User
from utils.password.pwd import Password


# ==================== Fixtures ====================

@pytest.fixture
def share_create_payload(test_directory_structure: dict[str, UUID]) -> dict:
    """基础分享创建请求体"""
    return {
        "file_id": str(test_directory_structure["file_id"]),
    }


# ==================== 认证测试 ====================

@pytest.mark.asyncio
async def test_share_create_requires_auth(async_client: AsyncClient):
    """创建分享需要认证"""
    response = await async_client.post(
        "/api/v1/share/",
        json={"file_id": str(uuid4())},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_share_list_requires_auth(async_client: AsyncClient):
    """列出分享需要认证"""
    response = await async_client.get("/api/v1/share/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_share_delete_requires_auth(async_client: AsyncClient):
    """删除分享需要认证"""
    response = await async_client.delete(f"/api/v1/share/{uuid4()}")
    assert response.status_code == 401


# ==================== 创建分享 ====================

@pytest.mark.asyncio
async def test_share_create_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID],
):
    """成功创建分享"""
    response = await async_client.post(
        "/api/v1/share/",
        headers=auth_headers,
        json={"file_id": str(test_directory_structure["file_id"])},
    )
    assert response.status_code == 200
    data = response.json()
    assert "share_id" in data


@pytest.mark.asyncio
async def test_share_create_with_password(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID],
):
    """创建带密码的分享"""
    response = await async_client.post(
        "/api/v1/share/",
        headers=auth_headers,
        json={
            "file_id": str(test_directory_structure["file_id"]),
            "password": "secret123",
        },
    )
    assert response.status_code == 200
    assert "share_id" in response.json()


@pytest.mark.asyncio
async def test_share_create_with_expiration(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID],
):
    """创建有过期时间的分享"""
    expires = (datetime.now() + timedelta(days=7)).isoformat()
    response = await async_client.post(
        "/api/v1/share/",
        headers=auth_headers,
        json={
            "file_id": str(test_directory_structure["file_id"]),
            "expires": expires,
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_share_create_with_download_limit(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID],
):
    """创建有下载次数限制的分享"""
    response = await async_client.post(
        "/api/v1/share/",
        headers=auth_headers,
        json={
            "file_id": str(test_directory_structure["file_id"]),
            "remain_downloads": 5,
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_share_create_nonexistent_file(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """分享不存在的文件返回 404"""
    response = await async_client.post(
        "/api/v1/share/",
        headers=auth_headers,
        json={"file_id": str(uuid4())},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_share_create_other_user_file(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
    test_directory_structure: dict[str, UUID],
):
    """分享他人的文件返回 404"""
    # 用管理员的认证头尝试分享测试用户的文件
    response = await async_client.post(
        "/api/v1/share/",
        headers=admin_headers,
        json={"file_id": str(test_directory_structure["file_id"])},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_share_create_folder(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID],
):
    """分享文件夹"""
    response = await async_client.post(
        "/api/v1/share/",
        headers=auth_headers,
        json={"file_id": str(test_directory_structure["docs_id"])},
    )
    assert response.status_code == 200


# ==================== 列出分享 ====================

@pytest.mark.asyncio
async def test_share_list_empty(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """无分享时列表为空"""
    response = await async_client.get(
        "/api/v1/share/",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_share_list_after_create(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID],
):
    """创建后能在列表中看到"""
    # 创建分享
    create_resp = await async_client.post(
        "/api/v1/share/",
        headers=auth_headers,
        json={"file_id": str(test_directory_structure["file_id"])},
    )
    assert create_resp.status_code == 200

    # 列出分享
    list_resp = await async_client.get(
        "/api/v1/share/",
        headers=auth_headers,
    )
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["count"] >= 1
    assert len(data["items"]) >= 1

    item = data["items"][0]
    assert "id" in item
    assert "code" in item
    assert "is_expired" in item
    assert "has_password" in item


@pytest.mark.asyncio
async def test_share_list_filter_expired(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    initialized_db: AsyncSession,
    test_directory_structure: dict[str, UUID],
):
    """过期筛选"""
    file_id = test_directory_structure["file_id"]

    # 创建一个已过期的分享
    user = await User.get(initialized_db, User.email == "testuser@example.com")
    expired_share = Share(
        code=uuid4(),
        file_id=file_id,
        user_id=user.id,
        expires=datetime.now() - timedelta(days=1),
    )
    await expired_share.save(initialized_db)

    # 创建一个未过期的分享
    valid_share = Share(
        code=uuid4(),
        file_id=file_id,
        user_id=user.id,
        expires=datetime.now() + timedelta(days=7),
    )
    await valid_share.save(initialized_db)

    # 筛选已过期
    resp_expired = await async_client.get(
        "/api/v1/share/",
        headers=auth_headers,
        params={"expired": "true"},
    )
    assert resp_expired.status_code == 200
    expired_items = resp_expired.json()["items"]
    for item in expired_items:
        assert item["is_expired"] is True

    # 筛选未过期
    resp_valid = await async_client.get(
        "/api/v1/share/",
        headers=auth_headers,
        params={"expired": "false"},
    )
    assert resp_valid.status_code == 200
    valid_items = resp_valid.json()["items"]
    for item in valid_items:
        assert item["is_expired"] is False


# ==================== 获取分享详情（公开） ====================

@pytest.mark.asyncio
async def test_share_get_detail(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    initialized_db: AsyncSession,
    test_directory_structure: dict[str, UUID],
):
    """获取分享详情（无需认证）"""
    # 先创建分享
    create_resp = await async_client.post(
        "/api/v1/share/",
        headers=auth_headers,
        json={"file_id": str(test_directory_structure["file_id"])},
    )
    share_id = create_resp.json()["share_id"]

    # 获取详情
    detail_resp = await async_client.get(f"/api/v1/share/{share_id}")
    assert detail_resp.status_code == 200

    data = detail_resp.json()
    assert "owner" in data
    assert "object" in data
    assert "children" in data
    assert "created_at" in data
    assert "preview_enabled" in data


@pytest.mark.asyncio
async def test_share_get_increments_views(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    initialized_db: AsyncSession,
    test_directory_structure: dict[str, UUID],
):
    """访问分享详情递增浏览次数"""
    # 创建分享
    create_resp = await async_client.post(
        "/api/v1/share/",
        headers=auth_headers,
        json={"file_id": str(test_directory_structure["file_id"])},
    )
    share_id = create_resp.json()["share_id"]

    # 访问两次
    await async_client.get(f"/api/v1/share/{share_id}")
    await async_client.get(f"/api/v1/share/{share_id}")

    # 检查 views（通过列表 API）
    list_resp = await async_client.get("/api/v1/share/", headers=auth_headers)
    items = list_resp.json()["items"]
    share_item = next(i for i in items if i["id"] == share_id)
    assert share_item["views"] >= 2


@pytest.mark.asyncio
async def test_share_get_nonexistent(async_client: AsyncClient):
    """获取不存在的分享返回 404"""
    response = await async_client.get(f"/api/v1/share/{uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_share_get_expired_returns_404(
    async_client: AsyncClient,
    initialized_db: AsyncSession,
    test_directory_structure: dict[str, UUID],
):
    """访问已过期的分享返回 404"""
    user = await User.get(initialized_db, User.email == "testuser@example.com")
    share = Share(
        code=uuid4(),
        file_id=test_directory_structure["file_id"],
        user_id=user.id,
        expires=datetime.now() - timedelta(hours=1),
    )
    share = await share.save(initialized_db)

    response = await async_client.get(f"/api/v1/share/{share.id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_share_get_with_password_no_password(
    async_client: AsyncClient,
    initialized_db: AsyncSession,
    test_directory_structure: dict[str, UUID],
):
    """访问带密码的分享但未提供密码返回 428"""
    user = await User.get(initialized_db, User.email == "testuser@example.com")
    share = Share(
        code=uuid4(),
        file_id=test_directory_structure["file_id"],
        user_id=user.id,
        password=Password.hash("secret"),
    )
    share = await share.save(initialized_db)

    response = await async_client.get(f"/api/v1/share/{share.id}")
    assert response.status_code == 428


@pytest.mark.asyncio
async def test_share_get_with_wrong_password(
    async_client: AsyncClient,
    initialized_db: AsyncSession,
    test_directory_structure: dict[str, UUID],
):
    """提供错误密码返回 403"""
    user = await User.get(initialized_db, User.email == "testuser@example.com")
    share = Share(
        code=uuid4(),
        file_id=test_directory_structure["file_id"],
        user_id=user.id,
        password=Password.hash("correct_password"),
    )
    share = await share.save(initialized_db)

    response = await async_client.get(
        f"/api/v1/share/{share.id}",
        params={"password": "wrong_password"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_share_get_with_correct_password(
    async_client: AsyncClient,
    initialized_db: AsyncSession,
    test_directory_structure: dict[str, UUID],
):
    """提供正确密码返回 200"""
    user = await User.get(initialized_db, User.email == "testuser@example.com")
    share = Share(
        code=uuid4(),
        file_id=test_directory_structure["file_id"],
        user_id=user.id,
        password=Password.hash("correct_password"),
    )
    share = await share.save(initialized_db)

    response = await async_client.get(
        f"/api/v1/share/{share.id}",
        params={"password": "correct_password"},
    )
    assert response.status_code == 200


# ==================== 删除分享 ====================

@pytest.mark.asyncio
async def test_share_delete_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID],
):
    """成功删除分享"""
    # 创建
    create_resp = await async_client.post(
        "/api/v1/share/",
        headers=auth_headers,
        json={"file_id": str(test_directory_structure["file_id"])},
    )
    share_id = create_resp.json()["share_id"]

    # 删除
    delete_resp = await async_client.delete(
        f"/api/v1/share/{share_id}",
        headers=auth_headers,
    )
    assert delete_resp.status_code == 204

    # 验证已删除
    get_resp = await async_client.get(f"/api/v1/share/{share_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_share_delete_nonexistent(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """删除不存在的分享返回 404"""
    response = await async_client.delete(
        f"/api/v1/share/{uuid4()}",
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_share_delete_other_user(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
    test_directory_structure: dict[str, UUID],
):
    """删除他人的分享返回 403"""
    # 用测试用户创建
    create_resp = await async_client.post(
        "/api/v1/share/",
        headers=auth_headers,
        json={"file_id": str(test_directory_structure["file_id"])},
    )
    share_id = create_resp.json()["share_id"]

    # 用管理员尝试删除
    delete_resp = await async_client.delete(
        f"/api/v1/share/{share_id}",
        headers=admin_headers,
    )
    assert delete_resp.status_code == 403
