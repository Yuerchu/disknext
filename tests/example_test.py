"""
示例测试文件

展示如何使用测试基础设施中的 fixtures 和工厂。
"""
import pytest
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from models.user import User
from models.group import Group
from models.object import Object, ObjectType
from tests.fixtures import UserFactory, GroupFactory, ObjectFactory


@pytest.mark.unit
async def test_user_factory(db_session: AsyncSession):
    """测试用户工厂的基本功能"""
    # 创建用户组
    group = await GroupFactory.create(db_session, name="测试组")

    # 创建用户
    user = await UserFactory.create(
        db_session,
        group_id=group.id,
        username="testuser",
        password="password123"
    )

    # 验证
    assert user.id is not None
    assert user.username == "testuser"
    assert user.group_id == group.id
    assert user.status is True


@pytest.mark.unit
async def test_group_factory(db_session: AsyncSession):
    """测试用户组工厂的基本功能"""
    # 创建管理员组
    admin_group = await GroupFactory.create_admin_group(db_session)

    # 验证
    assert admin_group.id is not None
    assert admin_group.admin is True
    assert admin_group.max_storage == 0  # 无限制


@pytest.mark.unit
async def test_object_factory(db_session: AsyncSession):
    """测试对象工厂的基本功能"""
    # 准备依赖
    from models.policy import Policy, PolicyType

    group = await GroupFactory.create(db_session)
    user = await UserFactory.create(db_session, group_id=group.id)

    policy = Policy(
        name="测试策略",
        type=PolicyType.LOCAL,
        server="/tmp/test",
    )
    policy = await policy.save(db_session)

    # 创建根目录
    root = await ObjectFactory.create_user_root(db_session, user, policy.id)

    # 创建子目录
    folder = await ObjectFactory.create_folder(
        db_session,
        owner_id=user.id,
        policy_id=policy.id,
        parent_id=root.id,
        name="documents"
    )

    # 创建文件
    file = await ObjectFactory.create_file(
        db_session,
        owner_id=user.id,
        policy_id=policy.id,
        parent_id=folder.id,
        name="test.txt",
        size=1024
    )

    # 验证
    assert root.parent_id is None
    assert folder.parent_id == root.id
    assert file.parent_id == folder.id
    assert file.type == ObjectType.FILE
    assert file.size == 1024


@pytest.mark.integration
async def test_conftest_fixtures(
    db_session: AsyncSession,
    test_user: dict[str, str | UUID],
    auth_headers: dict[str, str]
):
    """测试 conftest.py 中的 fixtures"""
    # 验证 test_user fixture
    assert test_user["id"] is not None
    assert test_user["username"] == "testuser"
    assert test_user["token"] is not None

    # 验证 auth_headers fixture
    assert "Authorization" in auth_headers
    assert auth_headers["Authorization"].startswith("Bearer ")

    # 验证用户在数据库中存在
    user = await User.get(db_session, User.id == test_user["id"])
    assert user is not None
    assert user.username == test_user["username"]


@pytest.mark.integration
async def test_test_directory_fixture(
    db_session: AsyncSession,
    test_user: dict[str, str | UUID],
    test_directory: dict[str, UUID]
):
    """测试 test_directory fixture"""
    # 验证目录结构
    assert "root" in test_directory
    assert "documents" in test_directory
    assert "work" in test_directory
    assert "personal" in test_directory
    assert "images" in test_directory
    assert "videos" in test_directory

    # 验证目录存在于数据库中
    documents = await Object.get(db_session, Object.id == test_directory["documents"])
    assert documents is not None
    assert documents.name == "documents"
    assert documents.type == ObjectType.FOLDER

    # 验证层级关系
    work = await Object.get(db_session, Object.id == test_directory["work"])
    assert work is not None
    assert work.parent_id == documents.id


@pytest.mark.integration
async def test_nested_structure_factory(db_session: AsyncSession):
    """测试嵌套结构工厂"""
    from models.policy import Policy, PolicyType

    # 准备依赖
    group = await GroupFactory.create(db_session)
    user = await UserFactory.create(db_session, group_id=group.id)

    policy = Policy(
        name="测试策略",
        type=PolicyType.LOCAL,
        server="/tmp/test",
    )
    policy = await policy.save(db_session)

    root = await ObjectFactory.create_user_root(db_session, user, policy.id)

    # 创建嵌套结构
    structure = await ObjectFactory.create_nested_structure(
        db_session,
        owner_id=user.id,
        policy_id=policy.id,
        root_id=root.id
    )

    # 验证结构
    assert "documents" in structure
    assert "work" in structure
    assert "personal" in structure
    assert "report" in structure
    assert "media" in structure
    assert "images" in structure
    assert "videos" in structure

    # 验证文件存在
    report = await Object.get(db_session, Object.id == structure["report"])
    assert report is not None
    assert report.name == "report.pdf"
    assert report.type == ObjectType.FILE
    assert report.size == 1024 * 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
