"""
Group 和 GroupOptions 模型的单元测试
"""
import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from models.group import Group, GroupOptions, GroupResponse


@pytest.mark.asyncio
async def test_group_create(db_session: AsyncSession):
    """测试创建用户组"""
    group = Group(
        name="测试用户组",
        max_storage=10240000,
        share_enabled=True,
        web_dav_enabled=False,
        admin=False,
        speed_limit=1024
    )
    group = await group.save(db_session)

    assert group.id is not None
    assert group.name == "测试用户组"
    assert group.max_storage == 10240000
    assert group.share_enabled is True
    assert group.web_dav_enabled is False
    assert group.admin is False
    assert group.speed_limit == 1024


@pytest.mark.asyncio
async def test_group_options_relationship(db_session: AsyncSession):
    """测试用户组与选项一对一关系"""
    # 创建用户组
    group = Group(name="有选项的组")
    group = await group.save(db_session)

    # 创建选项
    options = GroupOptions(
        group_id=group.id,
        share_download=True,
        share_free=True,
        relocate=False,
        source_batch=10,
        select_node=True,
        advance_delete=True,
        archive_download=True,
        webdav_proxy=False,
        aria2=True
    )
    options = await options.save(db_session)

    # 加载关系
    loaded_group = await Group.get(
        db_session,
        Group.id == group.id,
        load=Group.options
    )

    assert loaded_group.options is not None
    assert loaded_group.options.share_download is True
    assert loaded_group.options.aria2 is True
    assert loaded_group.options.source_batch == 10


@pytest.mark.asyncio
async def test_group_to_response(db_session: AsyncSession):
    """测试 to_response() DTO 转换"""
    # 创建用户组
    group = Group(
        name="响应测试组",
        share_enabled=True,
        web_dav_enabled=True
    )
    group = await group.save(db_session)

    # 创建选项
    options = GroupOptions(
        group_id=group.id,
        share_download=True,
        share_free=False,
        relocate=True,
        source_batch=5,
        select_node=False,
        advance_delete=True,
        archive_download=True,
        webdav_proxy=True,
        aria2=False
    )
    await options.save(db_session)

    # 重新加载以获取关系
    group = await Group.get(
        db_session,
        Group.id == group.id,
        load=Group.options
    )

    # 转换为响应 DTO
    response = group.to_response()

    assert isinstance(response, GroupResponse)
    assert response.id == group.id
    assert response.name == "响应测试组"
    assert response.allow_share is True
    assert response.webdav is True
    assert response.share_download is True
    assert response.share_free is False
    assert response.relocate is True
    assert response.source_batch == 5
    assert response.select_node is False
    assert response.advance_delete is True
    assert response.allow_archive_download is True
    assert response.allow_webdav_proxy is True
    assert response.allow_remote_download is False


@pytest.mark.asyncio
async def test_group_to_response_without_options(db_session: AsyncSession):
    """测试没有选项时 to_response() 返回默认值"""
    # 创建没有选项的用户组
    group = Group(name="无选项组")
    group = await group.save(db_session)

    # 加载关系（options 为 None）
    group = await Group.get(
        db_session,
        Group.id == group.id,
        load=Group.options
    )

    # 转换为响应 DTO
    response = group.to_response()

    assert isinstance(response, GroupResponse)
    assert response.share_download is False
    assert response.share_free is False
    assert response.source_batch == 0
    assert response.allow_remote_download is False


@pytest.mark.asyncio
async def test_group_policies_relationship(db_session: AsyncSession):
    """测试多对多关系（需要 Policy 模型）"""
    # 创建用户组
    group = Group(name="策略测试组")
    group = await group.save(db_session)

    # 注意: 这个测试需要 Policy 模型存在
    # 由于 Policy 模型在题目中没有提供，这里只做基本验证
    loaded_group = await Group.get(
        db_session,
        Group.id == group.id,
        load=Group.policies
    )

    # 验证关系字段存在且为空列表
    assert hasattr(loaded_group, 'policies')
    assert isinstance(loaded_group.policies, list)
    assert len(loaded_group.policies) == 0
