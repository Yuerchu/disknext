"""
User 模型的单元测试
"""
import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodels.user import AvatarType, User, UserBase, UserPublic, UserStatus
from sqlmodels.group import Group


@pytest.mark.asyncio
async def test_user_create(db_session: AsyncSession):
    """测试创建用户"""
    # 先创建用户组
    group = Group(name="默认组")
    group = await group.save(db_session)

    # 创建用户
    user = User(
        email="testuser@example.com",
        nickname="测试用户",
        group_id=group.id
    )
    user = await user.save(db_session)

    assert user.id is not None
    assert user.email == "testuser@example.com"
    assert user.nickname == "测试用户"
    assert user.status == UserStatus.ACTIVE
    assert user.storage == 0
    assert user.score == 0


@pytest.mark.asyncio
async def test_user_unique_email(db_session: AsyncSession):
    """测试邮箱唯一约束"""
    # 创建用户组
    group = Group(name="默认组")
    group = await group.save(db_session)

    # 创建第一个用户
    user1 = User(
        email="duplicate@example.com",
        nickname="用户1",
        group_id=group.id,
    )
    await user1.save(db_session)

    # 尝试创建同名用户
    user2 = User(
        email="duplicate@example.com",
        nickname="用户2",
        group_id=group.id,
    )

    with pytest.raises(IntegrityError):
        await user2.save(db_session)


@pytest.mark.asyncio
async def test_user_to_public(db_session: AsyncSession):
    """测试 to_public() DTO 转换"""
    # 创建用户组
    group = Group(name="测试组")
    group = await group.save(db_session)

    # 创建用户
    user = User(
        email="publicuser@example.com",
        nickname="公开用户",
        storage=1024,
        avatar=AvatarType.FILE,
        group_id=group.id
    )
    user = await user.save(db_session)

    # 预加载 group 关系后用 model_validate 构建 UserPublic
    loaded_user = await User.get(
        db_session,
        User.id == user.id,
        load=User.group
    )

    public_user = UserPublic.model_validate(
        loaded_user,
        from_attributes=True,
        update={'group_name': loaded_user.group.name},
    )

    assert isinstance(public_user, UserPublic)
    assert public_user.id == loaded_user.id
    assert public_user.email == "publicuser@example.com"
    assert public_user.nickname == "公开用户"
    assert public_user.storage == 1024


@pytest.mark.asyncio
async def test_user_group_relationship(db_session: AsyncSession):
    """测试用户与用户组关系"""
    # 创建用户组
    group = Group(name="VIP组")
    group = await group.save(db_session)

    # 创建用户
    user = User(
        email="vipuser@example.com",
        nickname="VIP用户",
        group_id=group.id,
    )
    user = await user.save(db_session)

    # 加载关系
    loaded_user = await User.get(
        db_session,
        User.id == user.id,
        load=User.group
    )

    assert loaded_user.group.name == "VIP组"
    assert loaded_user.group.id == group.id


@pytest.mark.asyncio
async def test_user_status_default(db_session: AsyncSession):
    """测试 status 默认值"""
    group = Group(name="默认组")
    group = await group.save(db_session)

    user = User(
        email="defaultuser@example.com",
        nickname="默认用户",
        group_id=group.id,
    )
    user = await user.save(db_session)

    assert user.status == UserStatus.ACTIVE


@pytest.mark.asyncio
async def test_user_storage_default(db_session: AsyncSession):
    """测试 storage 默认值"""
    group = Group(name="默认组")
    group = await group.save(db_session)

    user = User(
        email="storageuser@example.com",
        nickname="存储用户",
        group_id=group.id,
    )
    user = await user.save(db_session)

    assert user.storage == 0


@pytest.mark.asyncio
async def test_user_theme_preset(db_session: AsyncSession):
    """测试 theme_preset_id 字段默认为 None"""
    group = Group(name="默认组")
    group = await group.save(db_session)

    user = User(
        email="user1@example.com",
        nickname="主题用户",
        group_id=group.id,
    )
    user = await user.save(db_session)
    assert user.theme_preset_id is None


@pytest.mark.skip(reason="当前 email 字段为 NOT NULL，社交登录场景尚未实现")
@pytest.mark.asyncio
async def test_user_email_optional(db_session: AsyncSession):
    """测试 email 可以为空（支持社交登录用户）"""
    group = Group(name="默认组")
    group = await group.save(db_session)

    user = User(
        nickname="社交用户",
        group_id=group.id
    )
    user = await user.save(db_session)

    assert user.id is not None
    assert user.email is None


@pytest.mark.asyncio
async def test_user_phone_field(db_session: AsyncSession):
    """测试 phone 字段"""
    group = Group(name="默认组")
    group = await group.save(db_session)

    user = User(
        email="phoneuser@example.com",
        nickname="电话用户",
        phone="13800138000",
        group_id=group.id,
    )
    user = await user.save(db_session)

    assert user.phone == "13800138000"
