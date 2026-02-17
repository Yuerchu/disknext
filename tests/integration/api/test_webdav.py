"""
WebDAV 账户管理端点集成测试
"""
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodels import Group, GroupClaims, GroupOptions, Object, ObjectType, User
from sqlmodels.auth_identity import AuthIdentity, AuthProviderType
from sqlmodels.user import UserStatus
from utils import Password
from utils.JWT import create_access_token

API_PREFIX = "/api/v1/webdav"


# ==================== Fixtures ====================

@pytest_asyncio.fixture
async def no_webdav_headers(initialized_db: AsyncSession) -> dict[str, str]:
    """创建一个 WebDAV 被禁用的用户，返回其认证头"""
    group = Group(
        id=uuid4(),
        name="无WebDAV用户组",
        max_storage=1024 * 1024 * 1024,
        share_enabled=True,
        web_dav_enabled=False,
        admin=False,
        speed_limit=0,
    )
    initialized_db.add(group)
    await initialized_db.commit()
    await initialized_db.refresh(group)

    group_options = GroupOptions(
        group_id=group.id,
        share_download=True,
        share_free=False,
        relocate=False,
        source_batch=0,
        select_node=False,
        advance_delete=False,
    )
    initialized_db.add(group_options)
    await initialized_db.commit()
    await initialized_db.refresh(group_options)

    user = User(
        id=uuid4(),
        email="nowebdav@test.local",
        nickname="无WebDAV用户",
        status=UserStatus.ACTIVE,
        storage=0,
        score=0,
        group_id=group.id,
        avatar="default",
    )
    initialized_db.add(user)
    await initialized_db.commit()
    await initialized_db.refresh(user)

    identity = AuthIdentity(
        provider=AuthProviderType.EMAIL_PASSWORD,
        identifier="nowebdav@test.local",
        credential=Password.hash("nowebdav123"),
        is_primary=True,
        is_verified=True,
        user_id=user.id,
    )
    initialized_db.add(identity)

    from sqlmodels import Policy
    policy = await Policy.get(initialized_db, Policy.name == "本地存储")

    root = Object(
        id=uuid4(),
        name="/",
        type=ObjectType.FOLDER,
        owner_id=user.id,
        parent_id=None,
        policy_id=policy.id,
        size=0,
    )
    initialized_db.add(root)
    await initialized_db.commit()

    group.options = group_options
    group_claims = GroupClaims.from_group(group)
    result = create_access_token(
        sub=user.id,
        jti=uuid4(),
        status=user.status.value,
        group=group_claims,
    )
    return {"Authorization": f"Bearer {result.access_token}"}


# ==================== 认证测试 ====================

@pytest.mark.asyncio
async def test_list_accounts_requires_auth(async_client: AsyncClient):
    """测试获取账户列表需要认证"""
    response = await async_client.get(f"{API_PREFIX}/accounts")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_account_requires_auth(async_client: AsyncClient):
    """测试创建账户需要认证"""
    response = await async_client.post(
        f"{API_PREFIX}/accounts",
        json={"name": "test", "password": "testpass"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_account_requires_auth(async_client: AsyncClient):
    """测试更新账户需要认证"""
    response = await async_client.patch(
        f"{API_PREFIX}/accounts/1",
        json={"readonly": True},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_account_requires_auth(async_client: AsyncClient):
    """测试删除账户需要认证"""
    response = await async_client.delete(f"{API_PREFIX}/accounts/1")
    assert response.status_code == 401


# ==================== WebDAV 禁用测试 ====================

@pytest.mark.asyncio
async def test_list_accounts_webdav_disabled(
    async_client: AsyncClient,
    no_webdav_headers: dict[str, str],
):
    """测试 WebDAV 被禁用时返回 403"""
    response = await async_client.get(
        f"{API_PREFIX}/accounts",
        headers=no_webdav_headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_account_webdav_disabled(
    async_client: AsyncClient,
    no_webdav_headers: dict[str, str],
):
    """测试 WebDAV 被禁用时创建账户返回 403"""
    response = await async_client.post(
        f"{API_PREFIX}/accounts",
        headers=no_webdav_headers,
        json={"name": "test", "password": "testpass"},
    )
    assert response.status_code == 403


# ==================== 获取账户列表测试 ====================

@pytest.mark.asyncio
async def test_list_accounts_empty(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """测试初始状态账户列表为空"""
    response = await async_client.get(
        f"{API_PREFIX}/accounts",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json() == []


# ==================== 创建账户测试 ====================

@pytest.mark.asyncio
async def test_create_account_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """测试成功创建 WebDAV 账户"""
    response = await async_client.post(
        f"{API_PREFIX}/accounts",
        headers=auth_headers,
        json={"name": "my-nas", "password": "secretpass"},
    )
    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "my-nas"
    assert data["root"] == "/"
    assert data["readonly"] is False
    assert data["use_proxy"] is False
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_create_account_with_options(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """测试创建带选项的 WebDAV 账户"""
    response = await async_client.post(
        f"{API_PREFIX}/accounts",
        headers=auth_headers,
        json={
            "name": "readonly-nas",
            "password": "secretpass",
            "readonly": True,
            "use_proxy": True,
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "readonly-nas"
    assert data["readonly"] is True
    assert data["use_proxy"] is True


@pytest.mark.asyncio
async def test_create_account_duplicate_name(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """测试重名账户返回 409"""
    # 先创建一个
    response = await async_client.post(
        f"{API_PREFIX}/accounts",
        headers=auth_headers,
        json={"name": "dup-test", "password": "pass1"},
    )
    assert response.status_code == 201

    # 再创建同名的
    response = await async_client.post(
        f"{API_PREFIX}/accounts",
        headers=auth_headers,
        json={"name": "dup-test", "password": "pass2"},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_create_account_invalid_root(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """测试无效根目录路径返回 400"""
    response = await async_client.post(
        f"{API_PREFIX}/accounts",
        headers=auth_headers,
        json={
            "name": "bad-root",
            "password": "secretpass",
            "root": "/nonexistent/path",
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_account_with_valid_subdir(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID],
):
    """测试使用有效的子目录作为根路径"""
    response = await async_client.post(
        f"{API_PREFIX}/accounts",
        headers=auth_headers,
        json={
            "name": "docs-only",
            "password": "secretpass",
            "root": "/docs",
        },
    )
    assert response.status_code == 201
    assert response.json()["root"] == "/docs"


# ==================== 列表包含已创建账户测试 ====================

@pytest.mark.asyncio
async def test_list_accounts_after_create(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """测试创建后列表中包含该账户"""
    # 创建
    await async_client.post(
        f"{API_PREFIX}/accounts",
        headers=auth_headers,
        json={"name": "list-test", "password": "pass"},
    )

    # 列表
    response = await async_client.get(
        f"{API_PREFIX}/accounts",
        headers=auth_headers,
    )
    assert response.status_code == 200
    accounts = response.json()
    assert len(accounts) == 1
    assert accounts[0]["name"] == "list-test"


# ==================== 更新账户测试 ====================

@pytest.mark.asyncio
async def test_update_account_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """测试成功更新 WebDAV 账户"""
    # 创建
    create_resp = await async_client.post(
        f"{API_PREFIX}/accounts",
        headers=auth_headers,
        json={"name": "update-test", "password": "oldpass"},
    )
    account_id = create_resp.json()["id"]

    # 更新
    response = await async_client.patch(
        f"{API_PREFIX}/accounts/{account_id}",
        headers=auth_headers,
        json={"readonly": True},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["readonly"] is True
    assert data["name"] == "update-test"


@pytest.mark.asyncio
async def test_update_account_password(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """测试更新密码"""
    # 创建
    create_resp = await async_client.post(
        f"{API_PREFIX}/accounts",
        headers=auth_headers,
        json={"name": "pwd-test", "password": "oldpass"},
    )
    account_id = create_resp.json()["id"]

    # 更新密码
    response = await async_client.patch(
        f"{API_PREFIX}/accounts/{account_id}",
        headers=auth_headers,
        json={"password": "newpass123"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_update_account_root(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    test_directory_structure: dict[str, UUID],
):
    """测试更新根目录路径"""
    # 创建
    create_resp = await async_client.post(
        f"{API_PREFIX}/accounts",
        headers=auth_headers,
        json={"name": "root-update", "password": "pass"},
    )
    account_id = create_resp.json()["id"]

    # 更新 root 到有效子目录
    response = await async_client.patch(
        f"{API_PREFIX}/accounts/{account_id}",
        headers=auth_headers,
        json={"root": "/docs"},
    )
    assert response.status_code == 200
    assert response.json()["root"] == "/docs"


@pytest.mark.asyncio
async def test_update_account_invalid_root(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """测试更新为无效根目录返回 400"""
    # 创建
    create_resp = await async_client.post(
        f"{API_PREFIX}/accounts",
        headers=auth_headers,
        json={"name": "bad-root-update", "password": "pass"},
    )
    account_id = create_resp.json()["id"]

    # 更新到无效路径
    response = await async_client.patch(
        f"{API_PREFIX}/accounts/{account_id}",
        headers=auth_headers,
        json={"root": "/nonexistent"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_update_account_not_found(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """测试更新不存在的账户返回 404"""
    response = await async_client.patch(
        f"{API_PREFIX}/accounts/99999",
        headers=auth_headers,
        json={"readonly": True},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_other_user_account(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
):
    """测试更新其他用户的账户返回 404"""
    # 管理员创建账户
    create_resp = await async_client.post(
        f"{API_PREFIX}/accounts",
        headers=admin_headers,
        json={"name": "admin-account", "password": "pass"},
    )
    account_id = create_resp.json()["id"]

    # 普通用户尝试更新
    response = await async_client.patch(
        f"{API_PREFIX}/accounts/{account_id}",
        headers=auth_headers,
        json={"readonly": True},
    )
    assert response.status_code == 404


# ==================== 删除账户测试 ====================

@pytest.mark.asyncio
async def test_delete_account_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """测试成功删除 WebDAV 账户"""
    # 创建
    create_resp = await async_client.post(
        f"{API_PREFIX}/accounts",
        headers=auth_headers,
        json={"name": "delete-test", "password": "pass"},
    )
    account_id = create_resp.json()["id"]

    # 删除
    response = await async_client.delete(
        f"{API_PREFIX}/accounts/{account_id}",
        headers=auth_headers,
    )
    assert response.status_code == 204

    # 确认列表中已不存在
    list_resp = await async_client.get(
        f"{API_PREFIX}/accounts",
        headers=auth_headers,
    )
    assert list_resp.status_code == 200
    names = [a["name"] for a in list_resp.json()]
    assert "delete-test" not in names


@pytest.mark.asyncio
async def test_delete_account_not_found(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """测试删除不存在的账户返回 404"""
    response = await async_client.delete(
        f"{API_PREFIX}/accounts/99999",
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_other_user_account(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
):
    """测试删除其他用户的账户返回 404"""
    # 管理员创建账户
    create_resp = await async_client.post(
        f"{API_PREFIX}/accounts",
        headers=admin_headers,
        json={"name": "admin-del-test", "password": "pass"},
    )
    account_id = create_resp.json()["id"]

    # 普通用户尝试删除
    response = await async_client.delete(
        f"{API_PREFIX}/accounts/{account_id}",
        headers=auth_headers,
    )
    assert response.status_code == 404


# ==================== 多账户测试 ====================

@pytest.mark.asyncio
async def test_multiple_accounts(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """测试同一用户可以创建多个账户"""
    for name in ["account-1", "account-2", "account-3"]:
        response = await async_client.post(
            f"{API_PREFIX}/accounts",
            headers=auth_headers,
            json={"name": name, "password": "pass"},
        )
        assert response.status_code == 201

    # 列表应有3个
    response = await async_client.get(
        f"{API_PREFIX}/accounts",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert len(response.json()) == 3


# ==================== 用户隔离测试 ====================

@pytest.mark.asyncio
async def test_accounts_user_isolation(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
):
    """测试不同用户的账户相互隔离"""
    # 普通用户创建
    await async_client.post(
        f"{API_PREFIX}/accounts",
        headers=auth_headers,
        json={"name": "user-account", "password": "pass"},
    )

    # 管理员创建
    await async_client.post(
        f"{API_PREFIX}/accounts",
        headers=admin_headers,
        json={"name": "admin-account", "password": "pass"},
    )

    # 普通用户只看到自己的
    response = await async_client.get(
        f"{API_PREFIX}/accounts",
        headers=auth_headers,
    )
    assert response.status_code == 200
    accounts = response.json()
    assert len(accounts) == 1
    assert accounts[0]["name"] == "user-account"

    # 管理员只看到自己的
    response = await async_client.get(
        f"{API_PREFIX}/accounts",
        headers=admin_headers,
    )
    assert response.status_code == 200
    accounts = response.json()
    assert len(accounts) == 1
    assert accounts[0]["name"] == "admin-account"
