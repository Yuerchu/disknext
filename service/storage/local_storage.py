"""
本地存储服务

负责本地文件系统的物理操作：
- 目录创建
- 文件写入/读取/删除
- 文件移动（软删除到 .trash）

所有 IO 操作都使用 aiofiles 确保异步执行。
"""
from pathlib import Path
from uuid import UUID

import aiofiles
import aiofiles.os
from loguru import logger as l

from sqlmodels.policy import Policy
from .exceptions import (
    DirectoryCreationError,
    FileReadError,
    FileWriteError,
    InvalidPathError,
    StorageException,
    StorageFileNotFoundError,
)
from .naming_rule import NamingContext, NamingRuleParser


class LocalStorageService:
    """
    本地存储服务

    实现本地文件系统的异步文件操作。
    所有 IO 操作都使用 aiofiles 确保异步执行。

    使用示例::

        service = LocalStorageService(policy)
        await service.ensure_base_directory()

        dir_path, storage_name, full_path = await service.generate_file_path(
            user_id=user.id,
            original_filename="document.pdf",
        )
        await service.write_file(full_path, content)
    """

    def __init__(self, policy: Policy):
        """
        初始化本地存储服务

        :param policy: 存储策略配置
        :raises StorageException: 本地存储策略未指定 server 路径时抛出
        """
        if not policy.server:
            raise StorageException("本地存储策略必须指定 server 路径")

        self._policy = policy
        self._base_path = Path(policy.server).resolve()

    @property
    def base_path(self) -> Path:
        """存储根目录"""
        return self._base_path

    # ==================== 目录操作 ====================

    async def ensure_base_directory(self) -> None:
        """
        确保存储根目录存在

        创建策略时调用，确保物理目录已创建。

        :raises DirectoryCreationError: 目录创建失败时抛出
        """
        try:
            await aiofiles.os.makedirs(str(self._base_path), exist_ok=True)
            l.info(f"已确保存储目录存在: {self._base_path}")
        except OSError as e:
            raise DirectoryCreationError(f"无法创建存储目录 {self._base_path}: {e}")

    async def ensure_directory(self, relative_path: str) -> Path:
        """
        确保相对路径的目录存在

        :param relative_path: 相对于存储根目录的路径
        :return: 完整的目录路径
        :raises DirectoryCreationError: 目录创建失败时抛出
        """
        try:
            full_path = self._base_path / relative_path
            await aiofiles.os.makedirs(str(full_path), exist_ok=True)
            return full_path
        except OSError as e:
            raise DirectoryCreationError(f"无法创建目录 {relative_path}: {e}")

    async def ensure_trash_directory(self, user_id: UUID) -> Path:
        """
        确保用户的回收站目录存在

        回收站路径格式: {storage_root}/{user_id}/.trash

        :param user_id: 用户UUID
        :return: 回收站目录路径
        :raises DirectoryCreationError: 目录创建失败时抛出
        """
        trash_path = self._base_path / str(user_id) / ".trash"
        try:
            await aiofiles.os.makedirs(str(trash_path), exist_ok=True)
            return trash_path
        except OSError as e:
            raise DirectoryCreationError(f"无法创建回收站目录: {e}")

    # ==================== 路径生成 ====================

    async def generate_file_path(
        self,
        user_id: UUID,
        original_filename: str,
    ) -> tuple[str, str, str]:
        """
        根据命名规则生成文件存储路径

        :param user_id: 用户UUID
        :param original_filename: 原始文件名
        :return: (相对目录路径, 存储文件名, 完整物理路径)
        """
        context = NamingContext(
            user_id=user_id,
            original_filename=original_filename,
        )

        # 解析目录规则
        dir_path = ""
        if self._policy.dir_name_rule:
            dir_path = NamingRuleParser.parse(self._policy.dir_name_rule, context)

        # 解析文件名规则
        if self._policy.auto_rename and self._policy.file_name_rule:
            storage_name = NamingRuleParser.parse(self._policy.file_name_rule, context)
            # 确保有扩展名
            if '.' in original_filename and '.' not in storage_name:
                ext = original_filename.rsplit('.', 1)[1]
                storage_name = f"{storage_name}.{ext}"
        else:
            storage_name = original_filename

        # 确保目录存在
        if dir_path:
            full_dir = await self.ensure_directory(dir_path)
        else:
            full_dir = self._base_path

        full_path = str(full_dir / storage_name)

        return dir_path, storage_name, full_path

    # ==================== 文件写入 ====================

    async def write_file(self, path: str, content: bytes) -> int:
        """
        写入文件内容

        :param path: 完整文件路径
        :param content: 文件内容
        :return: 写入的字节数
        :raises FileWriteError: 写入失败时抛出
        """
        try:
            async with aiofiles.open(path, 'wb') as f:
                await f.write(content)
            return len(content)
        except OSError as e:
            raise FileWriteError(f"写入文件失败 {path}: {e}")

    async def write_file_chunk(
        self,
        path: str,
        content: bytes,
        offset: int,
    ) -> int:
        """
        写入文件分片

        :param path: 完整文件路径
        :param content: 分片内容
        :param offset: 写入偏移量
        :return: 写入的字节数
        :raises FileWriteError: 写入失败时抛出
        """
        try:
            # 检查文件是否存在，决定打开模式
            is_exists = await self.file_exists(path)
            mode = 'r+b' if is_exists else 'wb'

            async with aiofiles.open(path, mode) as f:
                await f.seek(offset)
                await f.write(content)
            return len(content)
        except OSError as e:
            raise FileWriteError(f"写入文件分片失败 {path}: {e}")

    async def create_empty_file(self, path: str) -> None:
        """
        创建空白文件

        :param path: 完整文件路径
        :raises FileWriteError: 创建失败时抛出
        """
        try:
            async with aiofiles.open(path, 'wb'):
                pass  # 创建空文件
        except OSError as e:
            raise FileWriteError(f"创建空文件失败 {path}: {e}")

    # ==================== 文件读取 ====================

    async def read_file(self, path: str) -> bytes:
        """
        读取完整文件

        :param path: 完整文件路径
        :return: 文件内容
        :raises StorageFileNotFoundError: 文件不存在时抛出
        :raises FileReadError: 读取失败时抛出
        """
        if not await self.file_exists(path):
            raise StorageFileNotFoundError(f"文件不存在: {path}")

        try:
            async with aiofiles.open(path, 'rb') as f:
                return await f.read()
        except OSError as e:
            raise FileReadError(f"读取文件失败 {path}: {e}")

    async def get_file_size(self, path: str) -> int:
        """
        获取文件大小

        :param path: 完整文件路径
        :return: 文件大小（字节）
        :raises StorageFileNotFoundError: 文件不存在时抛出
        """
        if not await self.file_exists(path):
            raise StorageFileNotFoundError(f"文件不存在: {path}")

        stat = await aiofiles.os.stat(path)
        return stat.st_size

    async def file_exists(self, path: str) -> bool:
        """
        检查文件是否存在

        :param path: 完整文件路径
        :return: 是否存在
        """
        return await aiofiles.os.path.exists(path)

    # ==================== 文件删除和移动 ====================

    async def delete_file(self, path: str) -> None:
        """
        删除文件（物理删除）

        :param path: 完整文件路径
        """
        if await self.file_exists(path):
            try:
                await aiofiles.os.remove(path)
                l.debug(f"已删除文件: {path}")
            except OSError as e:
                l.warning(f"删除文件失败 {path}: {e}")

    async def move_to_trash(
        self,
        source_path: str,
        user_id: UUID,
        object_id: UUID,
    ) -> str:
        """
        将文件移动到回收站（软删除）

        回收站中的文件名格式: {object_uuid}_{original_filename}

        :param source_path: 源文件完整路径
        :param user_id: 用户UUID
        :param object_id: 对象UUID（用于生成唯一的回收站文件名）
        :return: 回收站中的文件路径
        :raises StorageFileNotFoundError: 源文件不存在时抛出
        """
        if not await self.file_exists(source_path):
            raise StorageFileNotFoundError(f"源文件不存在: {source_path}")

        # 确保回收站目录存在
        trash_dir = await self.ensure_trash_directory(user_id)

        # 使用 object_id 作为回收站文件名前缀，避免冲突
        source_filename = Path(source_path).name
        trash_filename = f"{object_id}_{source_filename}"
        trash_path = trash_dir / trash_filename

        # 移动文件
        try:
            await aiofiles.os.rename(source_path, str(trash_path))
            l.info(f"文件已移动到回收站: {source_path} -> {trash_path}")
            return str(trash_path)
        except OSError as e:
            raise StorageException(f"移动文件到回收站失败: {e}")

    async def restore_from_trash(
        self,
        trash_path: str,
        restore_path: str,
    ) -> None:
        """
        从回收站恢复文件

        :param trash_path: 回收站中的文件路径
        :param restore_path: 恢复目标路径
        :raises StorageFileNotFoundError: 回收站文件不存在时抛出
        """
        if not await self.file_exists(trash_path):
            raise StorageFileNotFoundError(f"回收站文件不存在: {trash_path}")

        # 确保目标目录存在
        restore_dir = Path(restore_path).parent
        await aiofiles.os.makedirs(str(restore_dir), exist_ok=True)

        try:
            await aiofiles.os.rename(trash_path, restore_path)
            l.info(f"文件已从回收站恢复: {trash_path} -> {restore_path}")
        except OSError as e:
            raise StorageException(f"从回收站恢复文件失败: {e}")

    async def empty_trash(self, user_id: UUID) -> int:
        """
        清空用户回收站

        :param user_id: 用户UUID
        :return: 删除的文件数量
        """
        trash_dir = self._base_path / str(user_id) / ".trash"
        if not await aiofiles.os.path.exists(str(trash_dir)):
            return 0

        deleted_count = 0
        try:
            entries = await aiofiles.os.listdir(str(trash_dir))
            for entry in entries:
                file_path = trash_dir / entry
                if await aiofiles.os.path.isfile(str(file_path)):
                    await aiofiles.os.remove(str(file_path))
                    deleted_count += 1
            l.info(f"已清空用户 {user_id} 的回收站，删除 {deleted_count} 个文件")
        except OSError as e:
            l.warning(f"清空回收站时出错: {e}")

        return deleted_count

    # ==================== 路径验证 ====================

    def validate_path(self, path: str) -> bool:
        """
        验证路径是否在存储根目录下（防止路径遍历攻击）

        :param path: 要验证的路径
        :return: 路径是否有效
        """
        try:
            resolved = Path(path).resolve()
            return str(resolved).startswith(str(self._base_path))
        except (ValueError, OSError):
            return False

    def get_relative_path(self, full_path: str) -> str:
        """
        获取相对于存储根目录的相对路径

        :param full_path: 完整路径
        :return: 相对路径
        :raises InvalidPathError: 路径不在存储根目录下时抛出
        """
        if not self.validate_path(full_path):
            raise InvalidPathError(f"路径不在存储根目录下: {full_path}")

        resolved = Path(full_path).resolve()
        return str(resolved.relative_to(self._base_path))
