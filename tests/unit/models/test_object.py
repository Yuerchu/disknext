"""
Object 模型的单元测试
"""
import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from models.object import Object, ObjectType
from models.user import User
from models.group import Group


@pytest.mark.asyncio
async def test_object_create_folder(db_session: AsyncSession):
    """测试创建目录"""
    # 创建必要的依赖数据
    from models.policy import Policy, PolicyType

    group = Group(name="测试组")
    group = await group.save(db_session)

    user = User(username="testuser", password="password", group_id=group.id)
    user = await user.save(db_session)

    policy = Policy(
        name="本地策略",
        type=PolicyType.LOCAL,
        server="/tmp/test"
    )
    policy = await policy.save(db_session)

    # 创建目录
    folder = Object(
        name="测试目录",
        type=ObjectType.FOLDER,
        owner_id=user.id,
        policy_id=policy.id,
        size=0
    )
    folder = await folder.save(db_session)

    assert folder.id is not None
    assert folder.name == "测试目录"
    assert folder.type == ObjectType.FOLDER
    assert folder.size == 0


@pytest.mark.asyncio
async def test_object_create_file(db_session: AsyncSession):
    """测试创建文件"""
    from models.policy import Policy, PolicyType

    group = Group(name="测试组")
    group = await group.save(db_session)

    user = User(username="testuser", password="password", group_id=group.id)
    user = await user.save(db_session)

    policy = Policy(
        name="本地策略",
        type=PolicyType.LOCAL,
        server="/tmp/test"
    )
    policy = await policy.save(db_session)

    # 创建根目录
    root = Object(
        name=user.username,
        type=ObjectType.FOLDER,
        parent_id=None,
        owner_id=user.id,
        policy_id=policy.id
    )
    root = await root.save(db_session)

    # 创建文件
    file = Object(
        name="test.txt",
        type=ObjectType.FILE,
        parent_id=root.id,
        owner_id=user.id,
        policy_id=policy.id,
        size=1024,
        source_name="test_source.txt"
    )
    file = await file.save(db_session)

    assert file.id is not None
    assert file.name == "test.txt"
    assert file.type == ObjectType.FILE
    assert file.size == 1024
    assert file.source_name == "test_source.txt"


@pytest.mark.asyncio
async def test_object_is_file_property(db_session: AsyncSession):
    """测试 is_file 属性"""
    from models.policy import Policy, PolicyType

    group = Group(name="测试组")
    group = await group.save(db_session)

    user = User(username="testuser", password="password", group_id=group.id)
    user = await user.save(db_session)

    policy = Policy(name="本地策略", type=PolicyType.LOCAL, server="/tmp/test")
    policy = await policy.save(db_session)

    file = Object(
        name="file.txt",
        type=ObjectType.FILE,
        owner_id=user.id,
        policy_id=policy.id,
        size=100
    )
    file = await file.save(db_session)

    assert file.is_file is True
    assert file.is_folder is False


@pytest.mark.asyncio
async def test_object_is_folder_property(db_session: AsyncSession):
    """测试 is_folder 属性"""
    from models.policy import Policy, PolicyType

    group = Group(name="测试组")
    group = await group.save(db_session)

    user = User(username="testuser", password="password", group_id=group.id)
    user = await user.save(db_session)

    policy = Policy(name="本地策略", type=PolicyType.LOCAL, server="/tmp/test")
    policy = await policy.save(db_session)

    folder = Object(
        name="folder",
        type=ObjectType.FOLDER,
        owner_id=user.id,
        policy_id=policy.id
    )
    folder = await folder.save(db_session)

    assert folder.is_folder is True
    assert folder.is_file is False


@pytest.mark.asyncio
async def test_object_get_root(db_session: AsyncSession):
    """测试 get_root() 方法"""
    from models.policy import Policy, PolicyType

    group = Group(name="测试组")
    group = await group.save(db_session)

    user = User(username="rootuser", password="password", group_id=group.id)
    user = await user.save(db_session)

    policy = Policy(name="本地策略", type=PolicyType.LOCAL, server="/tmp/test")
    policy = await policy.save(db_session)

    # 创建根目录
    root = Object(
        name=user.username,
        type=ObjectType.FOLDER,
        parent_id=None,
        owner_id=user.id,
        policy_id=policy.id
    )
    root = await root.save(db_session)

    # 获取根目录
    fetched_root = await Object.get_root(db_session, user.id)

    assert fetched_root is not None
    assert fetched_root.id == root.id
    assert fetched_root.parent_id is None


@pytest.mark.asyncio
async def test_object_get_by_path_root(db_session: AsyncSession):
    """测试获取根目录"""
    from models.policy import Policy, PolicyType

    group = Group(name="测试组")
    group = await group.save(db_session)

    user = User(username="pathuser", password="password", group_id=group.id)
    user = await user.save(db_session)

    policy = Policy(name="本地策略", type=PolicyType.LOCAL, server="/tmp/test")
    policy = await policy.save(db_session)

    # 创建根目录
    root = Object(
        name=user.username,
        type=ObjectType.FOLDER,
        parent_id=None,
        owner_id=user.id,
        policy_id=policy.id
    )
    root = await root.save(db_session)

    # 通过路径获取根目录
    result = await Object.get_by_path(db_session, user.id, "/pathuser", user.username)

    assert result is not None
    assert result.id == root.id


@pytest.mark.asyncio
async def test_object_get_by_path_nested(db_session: AsyncSession):
    """测试获取嵌套路径"""
    from models.policy import Policy, PolicyType

    group = Group(name="测试组")
    group = await group.save(db_session)

    user = User(username="nesteduser", password="password", group_id=group.id)
    user = await user.save(db_session)

    policy = Policy(name="本地策略", type=PolicyType.LOCAL, server="/tmp/test")
    policy = await policy.save(db_session)

    # 创建目录结构: root -> docs -> work -> project
    root = Object(
        name=user.username,
        type=ObjectType.FOLDER,
        parent_id=None,
        owner_id=user.id,
        policy_id=policy.id
    )
    root = await root.save(db_session)

    docs = Object(
        name="docs",
        type=ObjectType.FOLDER,
        parent_id=root.id,
        owner_id=user.id,
        policy_id=policy.id
    )
    docs = await docs.save(db_session)

    work = Object(
        name="work",
        type=ObjectType.FOLDER,
        parent_id=docs.id,
        owner_id=user.id,
        policy_id=policy.id
    )
    work = await work.save(db_session)

    project = Object(
        name="project",
        type=ObjectType.FOLDER,
        parent_id=work.id,
        owner_id=user.id,
        policy_id=policy.id
    )
    project = await project.save(db_session)

    # 获取嵌套路径
    result = await Object.get_by_path(
        db_session,
        user.id,
        "/nesteduser/docs/work/project",
        user.username
    )

    assert result is not None
    assert result.id == project.id
    assert result.name == "project"


@pytest.mark.asyncio
async def test_object_get_by_path_not_found(db_session: AsyncSession):
    """测试路径不存在"""
    from models.policy import Policy, PolicyType

    group = Group(name="测试组")
    group = await group.save(db_session)

    user = User(username="notfounduser", password="password", group_id=group.id)
    user = await user.save(db_session)

    policy = Policy(name="本地策略", type=PolicyType.LOCAL, server="/tmp/test")
    policy = await policy.save(db_session)

    # 创建根目录
    root = Object(
        name=user.username,
        type=ObjectType.FOLDER,
        parent_id=None,
        owner_id=user.id,
        policy_id=policy.id
    )
    await root.save(db_session)

    # 获取不存在的路径
    result = await Object.get_by_path(
        db_session,
        user.id,
        "/notfounduser/nonexistent",
        user.username
    )

    assert result is None


@pytest.mark.asyncio
async def test_object_get_children(db_session: AsyncSession):
    """测试 get_children() 方法"""
    from models.policy import Policy, PolicyType

    group = Group(name="测试组")
    group = await group.save(db_session)

    user = User(username="childrenuser", password="password", group_id=group.id)
    user = await user.save(db_session)

    policy = Policy(name="本地策略", type=PolicyType.LOCAL, server="/tmp/test")
    policy = await policy.save(db_session)

    # 创建父目录
    parent = Object(
        name="parent",
        type=ObjectType.FOLDER,
        parent_id=None,
        owner_id=user.id,
        policy_id=policy.id
    )
    parent = await parent.save(db_session)

    # 创建子对象
    child1 = Object(
        name="child1.txt",
        type=ObjectType.FILE,
        parent_id=parent.id,
        owner_id=user.id,
        policy_id=policy.id,
        size=100
    )
    await child1.save(db_session)

    child2 = Object(
        name="child2",
        type=ObjectType.FOLDER,
        parent_id=parent.id,
        owner_id=user.id,
        policy_id=policy.id
    )
    await child2.save(db_session)

    # 获取子对象
    children = await Object.get_children(db_session, user.id, parent.id)

    assert len(children) == 2
    child_names = {c.name for c in children}
    assert child_names == {"child1.txt", "child2"}


@pytest.mark.asyncio
async def test_object_parent_child_relationship(db_session: AsyncSession):
    """测试父子关系"""
    from models.policy import Policy, PolicyType

    group = Group(name="测试组")
    group = await group.save(db_session)

    user = User(username="reluser", password="password", group_id=group.id)
    user = await user.save(db_session)

    policy = Policy(name="本地策略", type=PolicyType.LOCAL, server="/tmp/test")
    policy = await policy.save(db_session)

    # 创建父目录
    parent = Object(
        name="parent",
        type=ObjectType.FOLDER,
        owner_id=user.id,
        policy_id=policy.id
    )
    parent = await parent.save(db_session)

    # 创建子文件
    child = Object(
        name="child.txt",
        type=ObjectType.FILE,
        parent_id=parent.id,
        owner_id=user.id,
        policy_id=policy.id,
        size=50
    )
    child = await child.save(db_session)

    # 加载关系
    loaded_child = await Object.get(
        db_session,
        Object.id == child.id,
        load=Object.parent
    )

    assert loaded_child.parent is not None
    assert loaded_child.parent.id == parent.id


@pytest.mark.asyncio
async def test_object_unique_constraint(db_session: AsyncSession):
    """测试同目录名称唯一约束"""
    from models.policy import Policy, PolicyType

    group = Group(name="测试组")
    group = await group.save(db_session)

    user = User(username="uniqueuser", password="password", group_id=group.id)
    user = await user.save(db_session)

    policy = Policy(name="本地策略", type=PolicyType.LOCAL, server="/tmp/test")
    policy = await policy.save(db_session)

    # 创建父目录
    parent = Object(
        name="parent",
        type=ObjectType.FOLDER,
        owner_id=user.id,
        policy_id=policy.id
    )
    parent = await parent.save(db_session)

    # 创建第一个文件
    file1 = Object(
        name="duplicate.txt",
        type=ObjectType.FILE,
        parent_id=parent.id,
        owner_id=user.id,
        policy_id=policy.id,
        size=100
    )
    await file1.save(db_session)

    # 尝试在同一目录创建同名文件
    file2 = Object(
        name="duplicate.txt",
        type=ObjectType.FILE,
        parent_id=parent.id,
        owner_id=user.id,
        policy_id=policy.id,
        size=200
    )

    with pytest.raises(IntegrityError):
        await file2.save(db_session)
