"""
用户测试数据工厂

提供创建测试用户的便捷方法。
"""
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodels.user import User
from utils.password.pwd import Password


class UserFactory:
    """用户工厂类，用于创建各种类型的测试用户"""

    @staticmethod
    async def create(
        session: AsyncSession,
        group_id: UUID,
        email: str | None = None,
        password: str | None = None,
        **kwargs
    ) -> User:
        """
        创建普通用户

        参数:
            session: 数据库会话
            group_id: 用户组UUID
            email: 用户邮箱（默认: test_user_{随机}@test.local）
            password: 明文密码（默认: password123）
            **kwargs: 其他用户字段

        返回:
            User: 创建的用户实例
        """
        import uuid

        if email is None:
            email = f"test_user_{uuid.uuid4().hex[:8]}@test.local"

        if password is None:
            password = "password123"

        user = User(
            email=email,
            nickname=kwargs.get("nickname", email),
            password=Password.hash(password),
            status=kwargs.get("status", True),
            storage=kwargs.get("storage", 0),
            score=kwargs.get("score", 100),
            group_id=group_id,
            two_factor=kwargs.get("two_factor"),
            avatar=kwargs.get("avatar", "default"),
            group_expires=kwargs.get("group_expires"),
            theme=kwargs.get("theme", "system"),
            language=kwargs.get("language", "zh-CN"),
            timezone=kwargs.get("timezone", 8),
            previous_group_id=kwargs.get("previous_group_id"),
        )

        user = await user.save(session)
        return user

    @staticmethod
    async def create_admin(
        session: AsyncSession,
        admin_group_id: UUID,
        email: str | None = None,
        password: str | None = None
    ) -> User:
        """
        创建管理员用户

        参数:
            session: 数据库会话
            admin_group_id: 管理员组UUID
            email: 用户邮箱（默认: admin_{随机}@disknext.local）
            password: 明文密码（默认: admin_password）

        返回:
            User: 创建的管理员用户实例
        """
        import uuid

        if email is None:
            email = f"admin_{uuid.uuid4().hex[:8]}@disknext.local"

        if password is None:
            password = "admin_password"

        admin = User(
            email=email,
            nickname=f"管理员 {email}",
            password=Password.hash(password),
            status=True,
            storage=0,
            score=9999,
            group_id=admin_group_id,
            avatar="default",
        )

        admin = await admin.save(session)
        return admin

    @staticmethod
    async def create_banned(
        session: AsyncSession,
        group_id: UUID,
        email: str | None = None
    ) -> User:
        """
        创建被封禁用户

        参数:
            session: 数据库会话
            group_id: 用户组UUID
            email: 用户邮箱（默认: banned_user_{随机}@test.local）

        返回:
            User: 创建的被封禁用户实例
        """
        import uuid

        if email is None:
            email = f"banned_user_{uuid.uuid4().hex[:8]}@test.local"

        banned_user = User(
            email=email,
            nickname=f"封禁用户 {email}",
            password=Password.hash("banned_password"),
            status=False,  # 封禁状态
            storage=0,
            score=0,
            group_id=group_id,
            avatar="default",
        )

        banned_user = await banned_user.save(session)
        return banned_user

    @staticmethod
    async def create_with_storage(
        session: AsyncSession,
        group_id: UUID,
        storage_bytes: int,
        email: str | None = None
    ) -> User:
        """
        创建已使用指定存储空间的用户

        参数:
            session: 数据库会话
            group_id: 用户组UUID
            storage_bytes: 已使用的存储空间（字节）
            email: 用户邮箱（默认: storage_user_{随机}@test.local）

        返回:
            User: 创建的用户实例
        """
        import uuid

        if email is None:
            email = f"storage_user_{uuid.uuid4().hex[:8]}@test.local"

        user = User(
            email=email,
            nickname=email,
            password=Password.hash("password123"),
            status=True,
            storage=storage_bytes,
            score=100,
            group_id=group_id,
            avatar="default",
        )

        user = await user.save(session)
        return user
