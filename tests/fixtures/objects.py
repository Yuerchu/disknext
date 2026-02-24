"""
对象（文件/目录）测试数据工厂

提供创建测试对象的便捷方法。
"""
from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodels.object import Object, ObjectType
from sqlmodels.user import User


class ObjectFactory:
    """对象工厂类，用于创建测试文件和目录"""

    @staticmethod
    async def create_folder(
        session: AsyncSession,
        owner_id: UUID,
        policy_id: UUID,
        parent_id: UUID | None = None,
        name: str | None = None,
        **kwargs
    ) -> Object:
        """
        创建目录

        参数:
            session: 数据库会话
            owner_id: 所有者UUID
            policy_id: 存储策略UUID
            parent_id: 父目录UUID（None 表示根目录）
            name: 目录名称（默认: folder_{随机}）
            **kwargs: 其他对象字段

        返回:
            Object: 创建的目录实例
        """
        import uuid

        if name is None:
            name = f"folder_{uuid.uuid4().hex[:8]}"

        folder = Object(
            name=name,
            type=ObjectType.FOLDER,
            parent_id=parent_id,
            owner_id=owner_id,
            policy_id=policy_id,
            size=0,
            password=kwargs.get("password"),
        )

        folder = await folder.save(session)
        return folder

    @staticmethod
    async def create_file(
        session: AsyncSession,
        owner_id: UUID,
        policy_id: UUID,
        parent_id: UUID,
        name: str | None = None,
        size: int = 1024,
        **kwargs
    ) -> Object:
        """
        创建文件

        参数:
            session: 数据库会话
            owner_id: 所有者UUID
            policy_id: 存储策略UUID
            parent_id: 父目录UUID
            name: 文件名称（默认: file_{随机}.txt）
            size: 文件大小（字节，默认: 1024）
            **kwargs: 其他对象字段

        返回:
            Object: 创建的文件实例
        """
        import uuid

        if name is None:
            name = f"file_{uuid.uuid4().hex[:8]}.txt"

        file = Object(
            name=name,
            type=ObjectType.FILE,
            parent_id=parent_id,
            owner_id=owner_id,
            policy_id=policy_id,
            size=size,
            mime_type=kwargs.get("mime_type"),
            source_name=kwargs.get("source_name", name),
            upload_session_id=kwargs.get("upload_session_id"),
            password=kwargs.get("password"),
        )

        file = await file.save(session)
        return file

    @staticmethod
    async def create_user_root(
        session: AsyncSession,
        user: User,
        policy_id: UUID
    ) -> Object:
        """
        为用户创建根目录

        参数:
            session: 数据库会话
            user: 用户实例
            policy_id: 存储策略UUID

        返回:
            Object: 创建的根目录实例
        """
        root = Object(
            name="/",
            type=ObjectType.FOLDER,
            parent_id=None,
            owner_id=user.id,
            policy_id=policy_id,
            size=0,
        )

        root = await root.save(session)
        return root

    @staticmethod
    async def create_directory_tree(
        session: AsyncSession,
        owner_id: UUID,
        policy_id: UUID,
        root_id: UUID,
        depth: int = 2,
        folders_per_level: int = 2
    ) -> list[Object]:
        """
        创建目录树结构（递归）

        参数:
            session: 数据库会话
            owner_id: 所有者UUID
            policy_id: 存储策略UUID
            root_id: 根目录UUID
            depth: 树的深度（默认: 2）
            folders_per_level: 每层的目录数量（默认: 2）

        返回:
            list[Object]: 创建的所有目录列表
        """
        folders = []

        async def create_level(parent_id: UUID, current_depth: int):
            if current_depth <= 0:
                return

            for i in range(folders_per_level):
                folder = await ObjectFactory.create_folder(
                    session=session,
                    owner_id=owner_id,
                    policy_id=policy_id,
                    parent_id=parent_id,
                    name=f"level_{current_depth}_folder_{i}"
                )
                folders.append(folder)

                # 递归创建子目录
                await create_level(folder.id, current_depth - 1)

        await create_level(root_id, depth)
        return folders

    @staticmethod
    async def create_files_in_folder(
        session: AsyncSession,
        owner_id: UUID,
        policy_id: UUID,
        parent_id: UUID,
        count: int = 5,
        size_range: tuple[int, int] = (1024, 1024 * 1024)
    ) -> list[Object]:
        """
        在指定目录中创建多个文件

        参数:
            session: 数据库会话
            owner_id: 所有者UUID
            policy_id: 存储策略UUID
            parent_id: 父目录UUID
            count: 文件数量（默认: 5）
            size_range: 文件大小范围（字节，默认: 1KB - 1MB）

        返回:
            list[Object]: 创建的所有文件列表
        """
        import random

        files = []
        extensions = [".txt", ".pdf", ".jpg", ".png", ".mp4", ".zip", ".doc"]

        for i in range(count):
            ext = random.choice(extensions)
            size = random.randint(size_range[0], size_range[1])

            file = await ObjectFactory.create_file(
                session=session,
                owner_id=owner_id,
                policy_id=policy_id,
                parent_id=parent_id,
                name=f"test_file_{i}{ext}",
                size=size
            )
            files.append(file)

        return files

    @staticmethod
    async def create_large_file(
        session: AsyncSession,
        owner_id: UUID,
        policy_id: UUID,
        parent_id: UUID,
        size_mb: int = 100,
        name: str | None = None
    ) -> Object:
        """
        创建大文件（用于测试存储限制）

        参数:
            session: 数据库会话
            owner_id: 所有者UUID
            policy_id: 存储策略UUID
            parent_id: 父目录UUID
            size_mb: 文件大小（MB，默认: 100）
            name: 文件名称（默认: large_file_{size_mb}MB.bin）

        返回:
            Object: 创建的大文件实例
        """
        if name is None:
            name = f"large_file_{size_mb}MB.bin"

        size_bytes = size_mb * 1024 * 1024

        file = await ObjectFactory.create_file(
            session=session,
            owner_id=owner_id,
            policy_id=policy_id,
            parent_id=parent_id,
            name=name,
            size=size_bytes
        )

        return file

    @staticmethod
    async def create_nested_structure(
        session: AsyncSession,
        owner_id: UUID,
        policy_id: UUID,
        root_id: UUID
    ) -> dict[str, UUID]:
        """
        创建嵌套的目录和文件结构（用于测试路径解析）

        创建结构:
        root/
        ├── documents/
        │   ├── work/
        │   │   ├── report.pdf
        │   │   └── presentation.pptx
        │   └── personal/
        │       └── notes.txt
        └── media/
            ├── images/
            │   ├── photo1.jpg
            │   └── photo2.png
            └── videos/
                └── clip.mp4

        参数:
            session: 数据库会话
            owner_id: 所有者UUID
            policy_id: 存储策略UUID
            root_id: 根目录UUID

        返回:
            dict[str, UUID]: 创建的对象ID字典
        """
        result = {"root": root_id}

        # 创建 documents 目录
        documents = await ObjectFactory.create_folder(
            session, owner_id, policy_id, root_id, "documents"
        )
        result["documents"] = documents.id

        # 创建 documents/work 目录
        work = await ObjectFactory.create_folder(
            session, owner_id, policy_id, documents.id, "work"
        )
        result["work"] = work.id

        # 创建 documents/work 下的文件
        report = await ObjectFactory.create_file(
            session, owner_id, policy_id, work.id, "report.pdf", 1024 * 100
        )
        result["report"] = report.id

        presentation = await ObjectFactory.create_file(
            session, owner_id, policy_id, work.id, "presentation.pptx", 1024 * 500
        )
        result["presentation"] = presentation.id

        # 创建 documents/personal 目录
        personal = await ObjectFactory.create_folder(
            session, owner_id, policy_id, documents.id, "personal"
        )
        result["personal"] = personal.id

        notes = await ObjectFactory.create_file(
            session, owner_id, policy_id, personal.id, "notes.txt", 1024
        )
        result["notes"] = notes.id

        # 创建 media 目录
        media = await ObjectFactory.create_folder(
            session, owner_id, policy_id, root_id, "media"
        )
        result["media"] = media.id

        # 创建 media/images 目录
        images = await ObjectFactory.create_folder(
            session, owner_id, policy_id, media.id, "images"
        )
        result["images"] = images.id

        photo1 = await ObjectFactory.create_file(
            session, owner_id, policy_id, images.id, "photo1.jpg", 1024 * 200
        )
        result["photo1"] = photo1.id

        photo2 = await ObjectFactory.create_file(
            session, owner_id, policy_id, images.id, "photo2.png", 1024 * 300
        )
        result["photo2"] = photo2.id

        # 创建 media/videos 目录
        videos = await ObjectFactory.create_folder(
            session, owner_id, policy_id, media.id, "videos"
        )
        result["videos"] = videos.id

        clip = await ObjectFactory.create_file(
            session, owner_id, policy_id, videos.id, "clip.mp4", 1024 * 1024 * 10
        )
        result["clip"] = clip.id

        return result
