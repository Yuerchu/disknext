"""
用户组测试数据工厂

提供创建测试用户组的便捷方法。
"""
from sqlmodel.ext.asyncio.session import AsyncSession

from models.group import Group, GroupOptions


class GroupFactory:
    """用户组工厂类，用于创建各种类型的测试用户组"""

    @staticmethod
    async def create(
        session: AsyncSession,
        name: str | None = None,
        **kwargs
    ) -> Group:
        """
        创建用户组

        参数:
            session: 数据库会话
            name: 用户组名称（默认: test_group_{随机}）
            **kwargs: 其他用户组字段

        返回:
            Group: 创建的用户组实例
        """
        import uuid

        if name is None:
            name = f"test_group_{uuid.uuid4().hex[:8]}"

        group = Group(
            name=name,
            max_storage=kwargs.get("max_storage", 1024 * 1024 * 1024 * 10),  # 默认 10GB
            share_enabled=kwargs.get("share_enabled", True),
            web_dav_enabled=kwargs.get("web_dav_enabled", True),
            admin=kwargs.get("admin", False),
            speed_limit=kwargs.get("speed_limit", 0),
        )

        # 如果提供了选项参数，创建 GroupOptions
        if kwargs.get("create_options", False):
            group = await group.save(session, commit=False)
            options = GroupOptions(
                group_id=group.id,
                share_download=kwargs.get("share_download", True),
                share_free=kwargs.get("share_free", False),
                relocate=kwargs.get("relocate", True),
                source_batch=kwargs.get("source_batch", 10),
                select_node=kwargs.get("select_node", False),
                advance_delete=kwargs.get("advance_delete", False),
            )
            await options.save(session, commit=False)
            await session.commit()
        else:
            group = await group.save(session)

        return group

    @staticmethod
    async def create_admin_group(
        session: AsyncSession,
        name: str | None = None
    ) -> Group:
        """
        创建管理员组

        参数:
            session: 数据库会话
            name: 用户组名称（默认: admin_group_{随机}）

        返回:
            Group: 创建的管理员组实例
        """
        import uuid

        if name is None:
            name = f"admin_group_{uuid.uuid4().hex[:8]}"

        admin_group = Group(
            name=name,
            max_storage=0,  # 无限制
            share_enabled=True,
            web_dav_enabled=True,
            admin=True,
            speed_limit=0,
        )

        admin_group = await admin_group.save(session, commit=False)

        # 创建管理员组选项
        admin_options = GroupOptions(
            group_id=admin_group.id,
            share_download=True,
            share_free=True,
            relocate=True,
            source_batch=100,
            select_node=True,
            advance_delete=True,
            archive_download=True,
            archive_task=True,
            webdav_proxy=True,
            aria2=True,
            redirected_source=True,
        )
        await admin_options.save(session, commit=False)
        await session.commit()

        return admin_group

    @staticmethod
    async def create_limited_group(
        session: AsyncSession,
        max_storage: int,
        name: str | None = None
    ) -> Group:
        """
        创建有存储限制的用户组

        参数:
            session: 数据库会话
            max_storage: 最大存储空间（字节）
            name: 用户组名称（默认: limited_group_{随机}）

        返回:
            Group: 创建的用户组实例
        """
        import uuid

        if name is None:
            name = f"limited_group_{uuid.uuid4().hex[:8]}"

        limited_group = Group(
            name=name,
            max_storage=max_storage,
            share_enabled=True,
            web_dav_enabled=False,
            admin=False,
            speed_limit=1024,  # 1MB/s
        )

        limited_group = await limited_group.save(session, commit=False)

        # 创建限制组选项
        limited_options = GroupOptions(
            group_id=limited_group.id,
            share_download=False,
            share_free=False,
            relocate=False,
            source_batch=0,
            select_node=False,
            advance_delete=False,
        )
        await limited_options.save(session, commit=False)
        await session.commit()

        return limited_group

    @staticmethod
    async def create_free_group(
        session: AsyncSession,
        name: str | None = None
    ) -> Group:
        """
        创建免费用户组（无特殊权限）

        参数:
            session: 数据库会话
            name: 用户组名称（默认: free_group_{随机}）

        返回:
            Group: 创建的用户组实例
        """
        import uuid

        if name is None:
            name = f"free_group_{uuid.uuid4().hex[:8]}"

        free_group = Group(
            name=name,
            max_storage=1024 * 1024 * 1024,  # 1GB
            share_enabled=False,
            web_dav_enabled=False,
            admin=False,
            speed_limit=512,  # 512KB/s
        )

        free_group = await free_group.save(session, commit=False)

        # 创建免费组选项
        free_options = GroupOptions(
            group_id=free_group.id,
            share_download=False,
            share_free=False,
            relocate=False,
            source_batch=0,
            select_node=False,
            advance_delete=False,
        )
        await free_options.save(session, commit=False)
        await session.commit()

        return free_group
