"""
Share 模型单元测试

测试 Share 数据库模型的 CRUD 操作和 DTO 验证。
"""
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from faker import Faker
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodels.file import Entry, EntryType
from sqlmodels.group import Group
from sqlmodels.policy import Policy, PolicyType
from sqlmodels.share import (
    Share,
    ShareBase,
    ShareCreateRequest,
    CreateShareResponse,
    ShareOwnerInfo,
    ShareObjectItem,
    SharePublic,
    ShareResponse,
    ShareDetailResponse,
)
from sqlmodels.user import AvatarType, User, UserStatus


@pytest.fixture
def share_fixtures():
    """创建测试用 Share 所需的辅助数据工厂"""

    async def _create(session: AsyncSession, faker: Faker, **share_overrides):
        """创建一个完整的分享记录（含关联的 Group, Policy, User, Entry）"""
        group = Group(
            name=faker.unique.company(),
            max_storage=10 * 1024 * 1024 * 1024,
            share_enabled=True,
            web_dav_enabled=True,
            admin=False,
            speed_limit=0,
        )
        group = await group.save(session)

        policy = Policy(
            name=f"policy_{uuid4().hex[:8]}",
            type=PolicyType.LOCAL,
            server=f"/tmp/{uuid4()}",
            is_private=True,
            max_size=0,
        )
        policy = await policy.save(session)

        user = User(
            email=faker.unique.email(),
            nickname=faker.name(),
            status=UserStatus.ACTIVE,
            storage=0,
            score=100,
            group_id=group.id,
            password_hash="$argon2id$v=19$m=65536,t=3,p=4$stub",
        )
        user = await user.save(session)

        root = Entry(
            name="/",
            type=EntryType.FOLDER,
            parent_id=None,
            owner_id=user.id,
            policy_id=policy.id,
            size=0,
        )
        root = await root.save(session)

        file_entry = Entry(
            name="test_file.txt",
            type=EntryType.FILE,
            parent_id=root.id,
            owner_id=user.id,
            policy_id=policy.id,
            size=1024,
        )
        file_entry = await file_entry.save(session)

        defaults = {
            'code': uuid4(),
            'file_id': file_entry.id,
            'user_id': user.id,
        }
        defaults.update(share_overrides)

        share = Share(**defaults)
        share = await share.save(session)

        return {
            'share': share,
            'user': user,
            'file_entry': file_entry,
            'root': root,
            'policy': policy,
            'group': group,
        }

    return _create


# ==================== 数据库模型测试 ====================

class TestShareModel:
    """Share 数据库模型测试"""

    @pytest.mark.asyncio
    async def test_create_share(self, db_session: AsyncSession, faker: Faker, share_fixtures):
        """创建分享记录"""
        result = await share_fixtures(db_session, faker)
        share = result['share']

        assert share.id is not None
        assert share.code is not None
        assert share.views == 0
        assert share.downloads == 0
        assert share.preview_enabled is True
        assert share.score == 0
        assert share.password is None
        assert share.expires is None
        assert share.remain_downloads is None

    @pytest.mark.asyncio
    async def test_create_share_with_password(self, db_session: AsyncSession, faker: Faker, share_fixtures):
        """创建带密码的分享"""
        result = await share_fixtures(db_session, faker, password="hashed_password_123")
        share = result['share']

        assert share.password == "hashed_password_123"

    @pytest.mark.asyncio
    async def test_create_share_with_expiration(self, db_session: AsyncSession, faker: Faker, share_fixtures):
        """创建有过期时间的分享"""
        expires = datetime.now() + timedelta(days=7)
        result = await share_fixtures(db_session, faker, expires=expires)
        share = result['share']

        assert share.expires is not None

    @pytest.mark.asyncio
    async def test_create_share_with_download_limit(self, db_session: AsyncSession, faker: Faker, share_fixtures):
        """创建有下载次数限制的分享"""
        result = await share_fixtures(db_session, faker, remain_downloads=10)
        share = result['share']

        assert share.remain_downloads == 10

    @pytest.mark.asyncio
    async def test_share_code_unique(self, db_session: AsyncSession, faker: Faker, share_fixtures):
        """分享码唯一约束"""
        result1 = await share_fixtures(db_session, faker)
        code = result1['share'].code

        # 创建另一个使用相同 code 的分享应该失败
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError):
            await share_fixtures(db_session, faker, code=code)

    @pytest.mark.asyncio
    async def test_share_views_increment(self, db_session: AsyncSession, faker: Faker, share_fixtures):
        """浏览次数递增"""
        result = await share_fixtures(db_session, faker)
        share = result['share']

        share.views += 1
        share = await share.save(db_session)
        assert share.views == 1

        share.views += 1
        share = await share.save(db_session)
        assert share.views == 2

    @pytest.mark.asyncio
    async def test_share_delete(self, db_session: AsyncSession, faker: Faker, share_fixtures):
        """删除分享记录"""
        result = await share_fixtures(db_session, faker)
        share = result['share']
        share_id = share.id

        await Share.delete(db_session, share)

        deleted = await Share.get(db_session, Share.id == share_id)
        assert deleted is None

    @pytest.mark.asyncio
    async def test_share_score(self, db_session: AsyncSession, faker: Faker, share_fixtures):
        """分享积分设置"""
        result = await share_fixtures(db_session, faker, score=50)
        share = result['share']
        assert share.score == 50


# ==================== DTO 模型测试 ====================

class TestShareDTOs:
    """Share DTO 模型验证测试"""

    def test_share_create_request(self):
        """ShareCreateRequest 验证"""
        file_id = uuid4()
        req = ShareCreateRequest(
            file_id=file_id,
            password="test123",
            preview_enabled=False,
            score=10,
        )
        assert req.file_id == file_id
        assert req.password == "test123"
        assert req.preview_enabled is False
        assert req.score == 10
        assert req.expires is None
        assert req.remain_downloads is None

    def test_share_create_request_defaults(self):
        """ShareCreateRequest 默认值"""
        req = ShareCreateRequest(file_id=uuid4())
        assert req.password is None
        assert req.expires is None
        assert req.remain_downloads is None
        assert req.preview_enabled is True
        assert req.score == 0

    def test_create_share_response(self):
        """CreateShareResponse 验证"""
        share_id = uuid4()
        resp = CreateShareResponse(share_id=share_id)
        assert resp.share_id == share_id

    def test_share_owner_info(self):
        """ShareOwnerInfo 验证"""
        info = ShareOwnerInfo(
            user_id=uuid4(),
            nickname="测试用户",
            avatar=AvatarType.DEFAULT,
        )
        assert info.nickname == "测试用户"
        assert info.avatar == AvatarType.DEFAULT

    def test_share_owner_info_deleted_user(self):
        """ShareOwnerInfo 用户已删除时 user_id 为 None"""
        info = ShareOwnerInfo(
            user_id=None,
            nickname=None,
            avatar=AvatarType.DEFAULT,
        )
        assert info.user_id is None
        assert info.nickname is None

    def test_share_object_item(self):
        """ShareObjectItem 验证"""
        now = datetime.now()
        item = ShareObjectItem(
            id=uuid4(),
            name="document.pdf",
            type=EntryType.FILE,
            size=2048,
            created_at=now,
            updated_at=now,
        )
        assert item.name == "document.pdf"
        assert item.type == EntryType.FILE
        assert item.size == 2048

    def test_share_response(self):
        """ShareResponse 包含 is_expired 和 has_password"""
        now = datetime.now()
        resp = ShareResponse(
            id=uuid4(),
            code=uuid4(),
            views=10,
            downloads=5,
            remain_downloads=None,
            expires=None,
            preview_enabled=True,
            score=0,
            has_password=False,
            created_at=now,
            file_id=uuid4(),
            is_expired=False,
        )
        assert resp.is_expired is False
        assert resp.has_password is False

    def test_share_response_expired(self):
        """ShareResponse 过期标记"""
        past = datetime.now() - timedelta(days=1)
        resp = ShareResponse(
            id=uuid4(),
            code=uuid4(),
            views=0,
            downloads=0,
            remain_downloads=None,
            expires=past,
            preview_enabled=True,
            score=0,
            has_password=True,
            created_at=datetime.now(),
            file_id=uuid4(),
            is_expired=True,
        )
        assert resp.is_expired is True
        assert resp.has_password is True

    def test_share_detail_response(self):
        """ShareDetailResponse 包含 owner 和 children"""
        now = datetime.now()
        resp = ShareDetailResponse(
            created_at=now,
            expires=None,
            preview_enabled=True,
            score=0,
            owner=ShareOwnerInfo(user_id=uuid4(), nickname="Test", avatar=AvatarType.DEFAULT),
            object=ShareObjectItem(
                id=uuid4(), name="folder", type=EntryType.FOLDER,
                size=0, created_at=now, updated_at=now,
            ),
            children=[
                ShareObjectItem(
                    id=uuid4(), name="file.txt", type=EntryType.FILE,
                    size=100, created_at=now, updated_at=now,
                ),
            ],
        )
        assert resp.owner.nickname == "Test"
        assert len(resp.children) == 1
        assert resp.children[0].name == "file.txt"
