"""
File 模型的单元测试
"""
import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodels.file import Entry, EntryType
from sqlmodels.user import User
from sqlmodels.group import Group


@pytest.mark.asyncio
async def test_object_create_folder(db_session: AsyncSession):
    """测试创建目录"""
    # 创建必要的依赖数据
    from sqlmodels.policy import Policy, PolicyType

    group = Group(name="测试组")
    group = await group.save(db_session)

    user = User(email="testuser", group_id=group.id)
    user = await user.save(db_session)

    policy = Policy(
        name="本地策略",
        type=PolicyType.LOCAL,
        server="/tmp/test"
    )
    policy = await policy.save(db_session)

    # 创建目录
    folder = Entry(
        name="测试目录",
        type=EntryType.FOLDER,
        owner_id=user.id,
        policy_id=policy.id,
        size=0
    )
    folder = await folder.save(db_session)

    assert folder.id is not None
    assert folder.name == "测试目录"
    assert folder.type == EntryType.FOLDER
    assert folder.size == 0


@pytest.mark.asyncio
async def test_object_create_file(db_session: AsyncSession):
    """测试创建文件"""
    from sqlmodels.policy import Policy, PolicyType

    group = Group(name="测试组")
    group = await group.save(db_session)

    user = User(email="testuser", group_id=group.id)
    user = await user.save(db_session)

    policy = Policy(
        name="本地策略",
        type=PolicyType.LOCAL,
        server="/tmp/test"
    )
    policy = await policy.save(db_session)

    # 创建根目录
    root = Entry(
        name="/",
        type=EntryType.FOLDER,
        parent_id=None,
        owner_id=user.id,
        policy_id=policy.id
    )
    root = await root.save(db_session)

    # 创建文件
    file = Entry(
        name="test.txt",
        type=EntryType.FILE,
        parent_id=root.id,
        owner_id=user.id,
        policy_id=policy.id,
        size=1024,
    )
    file = await file.save(db_session)

    assert file.id is not None
    assert file.name == "test.txt"
    assert file.type == EntryType.FILE
    assert file.size == 1024


@pytest.mark.asyncio
async def test_object_is_file_property(db_session: AsyncSession):
    """测试 is_file 属性"""
    from sqlmodels.policy import Policy, PolicyType

    group = Group(name="测试组")
    group = await group.save(db_session)

    user = User(email="testuser", group_id=group.id)
    user = await user.save(db_session)

    policy = Policy(name="本地策略", type=PolicyType.LOCAL, server="/tmp/test")
    policy = await policy.save(db_session)

    file = Entry(
        name="file.txt",
        type=EntryType.FILE,
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
    from sqlmodels.policy import Policy, PolicyType

    group = Group(name="测试组")
    group = await group.save(db_session)

    user = User(email="testuser", group_id=group.id)
    user = await user.save(db_session)

    policy = Policy(name="本地策略", type=PolicyType.LOCAL, server="/tmp/test")
    policy = await policy.save(db_session)

    folder = Entry(
        name="folder",
        type=EntryType.FOLDER,
        owner_id=user.id,
        policy_id=policy.id
    )
    folder = await folder.save(db_session)

    assert folder.is_folder is True
    assert folder.is_file is False


@pytest.mark.asyncio
async def test_object_get_root(db_session: AsyncSession):
    """测试 get_root() 方法"""
    from sqlmodels.policy import Policy, PolicyType

    group = Group(name="测试组")
    group = await group.save(db_session)

    user = User(email="rootuser", group_id=group.id)
    user = await user.save(db_session)

    policy = Policy(name="本地策略", type=PolicyType.LOCAL, server="/tmp/test")
    policy = await policy.save(db_session)

    # 创建根目录
    root = Entry(
        name="/",
        type=EntryType.FOLDER,
        parent_id=None,
        owner_id=user.id,
        policy_id=policy.id
    )
    root = await root.save(db_session)

    # 获取根目录
    fetched_root = await Entry.get_root(db_session, user.id)

    assert fetched_root is not None
    assert fetched_root.id == root.id
    assert fetched_root.parent_id is None


@pytest.mark.asyncio
async def test_object_get_by_path_root(db_session: AsyncSession):
    """测试获取根目录"""
    from sqlmodels.policy import Policy, PolicyType

    group = Group(name="测试组")
    group = await group.save(db_session)

    user = User(email="pathuser", group_id=group.id)
    user = await user.save(db_session)

    policy = Policy(name="本地策略", type=PolicyType.LOCAL, server="/tmp/test")
    policy = await policy.save(db_session)

    # 创建根目录
    root = Entry(
        name="/",
        type=EntryType.FOLDER,
        parent_id=None,
        owner_id=user.id,
        policy_id=policy.id
    )
    root = await root.save(db_session)

    # 通过路径获取根目录
    result = await Entry.get_by_path(db_session, user.id, "/")

    assert result is not None
    assert result.id == root.id


@pytest.mark.asyncio
async def test_object_get_by_path_nested(db_session: AsyncSession):
    """测试获取嵌套路径"""
    from sqlmodels.policy import Policy, PolicyType

    group = Group(name="测试组")
    group = await group.save(db_session)

    user = User(email="nesteduser", group_id=group.id)
    user = await user.save(db_session)

    policy = Policy(name="本地策略", type=PolicyType.LOCAL, server="/tmp/test")
    policy = await policy.save(db_session)

    # 创建目录结构: root -> docs -> work -> project
    root = Entry(
        name="/",
        type=EntryType.FOLDER,
        parent_id=None,
        owner_id=user.id,
        policy_id=policy.id
    )
    root = await root.save(db_session)

    docs = Entry(
        name="docs",
        type=EntryType.FOLDER,
        parent_id=root.id,
        owner_id=user.id,
        policy_id=policy.id
    )
    docs = await docs.save(db_session)

    work = Entry(
        name="work",
        type=EntryType.FOLDER,
        parent_id=docs.id,
        owner_id=user.id,
        policy_id=policy.id
    )
    work = await work.save(db_session)

    project = Entry(
        name="project",
        type=EntryType.FOLDER,
        parent_id=work.id,
        owner_id=user.id,
        policy_id=policy.id
    )
    project = await project.save(db_session)

    # 获取嵌套路径
    result = await Entry.get_by_path(
        db_session,
        user.id,
        "/docs/work/project",
    )

    assert result is not None
    assert result.id == project.id
    assert result.name == "project"


@pytest.mark.asyncio
async def test_object_get_by_path_not_found(db_session: AsyncSession):
    """测试路径不存在"""
    from sqlmodels.policy import Policy, PolicyType

    group = Group(name="测试组")
    group = await group.save(db_session)

    user = User(email="notfounduser", group_id=group.id)
    user = await user.save(db_session)

    policy = Policy(name="本地策略", type=PolicyType.LOCAL, server="/tmp/test")
    policy = await policy.save(db_session)

    # 创建根目录
    root = Entry(
        name="/",
        type=EntryType.FOLDER,
        parent_id=None,
        owner_id=user.id,
        policy_id=policy.id
    )
    await root.save(db_session)

    # 获取不存在的路径
    result = await Entry.get_by_path(
        db_session,
        user.id,
        "/nonexistent",
    )

    assert result is None


@pytest.mark.asyncio
async def test_object_get_children(db_session: AsyncSession):
    """测试 get_children() 方法"""
    from sqlmodels.policy import Policy, PolicyType

    group = Group(name="测试组")
    group = await group.save(db_session)

    user = User(email="childrenuser", group_id=group.id)
    user = await user.save(db_session)

    policy = Policy(name="本地策略", type=PolicyType.LOCAL, server="/tmp/test")
    policy = await policy.save(db_session)

    # 创建父目录
    parent = Entry(
        name="parent",
        type=EntryType.FOLDER,
        parent_id=None,
        owner_id=user.id,
        policy_id=policy.id
    )
    parent = await parent.save(db_session)

    # 创建子对象
    child1 = Entry(
        name="child1.txt",
        type=EntryType.FILE,
        parent_id=parent.id,
        owner_id=user.id,
        policy_id=policy.id,
        size=100
    )
    await child1.save(db_session)

    child2 = Entry(
        name="child2",
        type=EntryType.FOLDER,
        parent_id=parent.id,
        owner_id=user.id,
        policy_id=policy.id
    )
    await child2.save(db_session)

    # 获取子对象
    children = await Entry.get_children(db_session, user.id, parent.id)

    assert len(children) == 2
    child_names = {c.name for c in children}
    assert child_names == {"child1.txt", "child2"}


@pytest.mark.asyncio
async def test_object_parent_child_relationship(db_session: AsyncSession):
    """测试父子关系"""
    from sqlmodels.policy import Policy, PolicyType

    group = Group(name="测试组")
    group = await group.save(db_session)

    user = User(email="reluser", group_id=group.id)
    user = await user.save(db_session)

    policy = Policy(name="本地策略", type=PolicyType.LOCAL, server="/tmp/test")
    policy = await policy.save(db_session)

    # 创建父目录
    parent = Entry(
        name="parent",
        type=EntryType.FOLDER,
        owner_id=user.id,
        policy_id=policy.id
    )
    parent = await parent.save(db_session)

    # 创建子文件
    child = Entry(
        name="child.txt",
        type=EntryType.FILE,
        parent_id=parent.id,
        owner_id=user.id,
        policy_id=policy.id,
        size=50
    )
    child = await child.save(db_session)

    # 加载关系
    loaded_child = await Entry.get(
        db_session,
        Entry.id == child.id,
        load=Entry.parent
    )

    assert loaded_child.parent is not None
    assert loaded_child.parent.id == parent.id


@pytest.mark.asyncio
async def test_object_unique_constraint(db_session: AsyncSession):
    """测试同目录名称唯一约束"""
    from sqlmodels.policy import Policy, PolicyType

    group = Group(name="测试组")
    group = await group.save(db_session)

    user = User(email="uniqueuser", group_id=group.id)
    user = await user.save(db_session)

    policy = Policy(name="本地策略", type=PolicyType.LOCAL, server="/tmp/test")
    policy = await policy.save(db_session)

    # 创建父目录
    parent = Entry(
        name="parent",
        type=EntryType.FOLDER,
        owner_id=user.id,
        policy_id=policy.id
    )
    parent = await parent.save(db_session)

    # 创建第一个文件
    file1 = Entry(
        name="duplicate.txt",
        type=EntryType.FILE,
        parent_id=parent.id,
        owner_id=user.id,
        policy_id=policy.id,
        size=100
    )
    await file1.save(db_session)

    # 尝试在同一目录创建同名文件
    file2 = Entry(
        name="duplicate.txt",
        type=EntryType.FILE,
        parent_id=parent.id,
        owner_id=user.id,
        policy_id=policy.id,
        size=200
    )

    with pytest.raises(IntegrityError):
        await file2.save(db_session)


@pytest.mark.asyncio
async def test_object_get_full_path(db_session: AsyncSession):
    """测试 get_full_path() 方法"""
    from sqlmodels.policy import Policy, PolicyType

    group = Group(name="测试组")
    group = await group.save(db_session)

    user = User(email="pathuser", group_id=group.id)
    user = await user.save(db_session)

    policy = Policy(name="本地策略", type=PolicyType.LOCAL, server="/tmp/test")
    policy = await policy.save(db_session)

    # 创建目录结构: root -> docs -> images -> photo.jpg
    root = Entry(
        name="/",
        type=EntryType.FOLDER,
        parent_id=None,
        owner_id=user.id,
        policy_id=policy.id
    )
    root = await root.save(db_session)

    docs = Entry(
        name="docs",
        type=EntryType.FOLDER,
        parent_id=root.id,
        owner_id=user.id,
        policy_id=policy.id
    )
    docs = await docs.save(db_session)

    images = Entry(
        name="images",
        type=EntryType.FOLDER,
        parent_id=docs.id,
        owner_id=user.id,
        policy_id=policy.id
    )
    images = await images.save(db_session)

    photo = Entry(
        name="photo.jpg",
        type=EntryType.FILE,
        parent_id=images.id,
        owner_id=user.id,
        policy_id=policy.id,
        size=2048
    )
    photo = await photo.save(db_session)

    # 测试完整路径
    full_path = await photo.get_full_path(db_session)
    assert full_path == "/docs/images/photo.jpg"

    # 测试根目录的 full_path
    root_path = await root.get_full_path(db_session)
    assert root_path == "/"
