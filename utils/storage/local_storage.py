"""
本地存储驱动

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

from .base import StorageDriver
from .exceptions import (
    DirectoryCreationError,
    FileReadError,
    FileWriteError,
    InvalidPathError,
    StorageException,
    StorageFileNotFoundError,
)
from .models import ChunkResult, DownloadKind, DownloadResult, UploadContext


class LocalStorageDriver(StorageDriver):
    """
    本地存储驱动

    实现本地文件系统的异步文件操作。
    所有 IO 操作都使用 aiofiles 确保异步执行。

    使用示例::

        driver = LocalStorageDriver(policy)
        await driver.ensure_base_directory()

        dir_path, storage_name, full_path = await driver.generate_path(
            user_id=user.id,
            original_filename="document.pdf",
        )
        await driver.write(full_path, content)
    """

    def __init__(self, policy: Policy) -> None:
        super().__init__(policy)
        if not policy.server:
            raise StorageException("本地存储策略必须指定 server 路径")
        self._base_path = Path(policy.server).resolve()

    @property
    def base_path(self) -> Path:
        """存储根目录"""
        return self._base_path

    # ==================== 能力声明 ====================

    @property
    def is_supports_direct_serving(self) -> bool:
        return True

    # ==================== 路径组装 ====================

    async def _assemble_path(self, dir_path: str, storage_name: str) -> str:
        """Local：拼接本地路径 + 确保目录存在"""
        if dir_path:
            full_dir = await self.ensure_directory(dir_path)
        else:
            full_dir = self._base_path
        return str(full_dir / storage_name)

    # ==================== 目录操作 ====================

    async def ensure_base_directory(self) -> None:
        """
        确保存储根目录存在

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

    # ==================== 核心 I/O ====================

    async def write(self, path: str, content: bytes) -> int:
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

    async def read(self, path: str) -> bytes:
        """
        读取完整文件

        :param path: 完整文件路径
        :return: 文件内容
        :raises StorageFileNotFoundError: 文件不存在时抛出
        :raises FileReadError: 读取失败时抛出
        """
        if not await self.exists(path):
            raise StorageFileNotFoundError(f"文件不存在: {path}")
        try:
            async with aiofiles.open(path, 'rb') as f:
                return await f.read()
        except OSError as e:
            raise FileReadError(f"读取文件失败 {path}: {e}")

    async def delete(self, path: str) -> None:
        """
        删除文件（物理删除）

        :param path: 完整文件路径
        """
        if await self.exists(path):
            try:
                await aiofiles.os.remove(path)
                l.debug(f"已删除文件: {path}")
                await self._cleanup_empty_parents(path)
            except OSError as e:
                l.warning(f"删除文件失败 {path}: {e}")

    async def exists(self, path: str) -> bool:
        """
        检查文件是否存在

        :param path: 完整文件路径
        :return: 是否存在
        """
        return await aiofiles.os.path.exists(path)

    async def get_size(self, path: str) -> int:
        """
        获取文件大小

        :param path: 完整文件路径
        :return: 文件大小（字节）
        :raises StorageFileNotFoundError: 文件不存在时抛出
        """
        if not await self.exists(path):
            raise StorageFileNotFoundError(f"文件不存在: {path}")
        stat = await aiofiles.os.stat(path)
        return stat.st_size

    async def create_empty(self, path: str) -> None:
        """
        创建空白文件

        :param path: 完整文件路径
        :raises FileWriteError: 创建失败时抛出
        """
        try:
            async with aiofiles.open(path, 'wb'):
                pass
        except OSError as e:
            raise FileWriteError(f"创建空文件失败 {path}: {e}")

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

    # ==================== 分片上传生命周期 ====================

    async def init_upload(
        self,
        path: str,
        total_size: int,
        chunk_size: int,
        content_type: str = 'application/octet-stream',
    ) -> UploadContext:
        """Local 不需要特殊初始化"""
        return UploadContext(
            path=path,
            total_size=total_size,
            chunk_size=chunk_size,
        )

    async def upload_chunk(
        self,
        ctx: UploadContext,
        chunk_index: int,
        content: bytes,
    ) -> ChunkResult:
        """Local：在 offset 处写入分片"""
        offset = chunk_index * ctx.chunk_size
        try:
            is_file_exists = await self.exists(ctx.path)
            mode = 'r+b' if is_file_exists else 'wb'
            async with aiofiles.open(ctx.path, mode) as f:
                await f.seek(offset)
                await f.write(content)
            return ChunkResult(bytes_written=len(content))
        except OSError as e:
            raise FileWriteError(f"写入文件分片失败 {ctx.path}: {e}")

    async def complete_upload(self, ctx: UploadContext) -> None:
        """Local：文件已在最终位置，无需额外操作"""

    async def abort_upload(self, ctx: UploadContext) -> None:
        """Local：删除已部分写入的文件"""
        await self.delete(ctx.path)

    # ==================== 下载 ====================

    async def get_download_result(self, path: str, filename: str) -> DownloadResult:
        """Local：返回本地文件路径"""
        return DownloadResult(
            kind=DownloadKind.FILE_PATH,
            file_path=path,
            filename=filename,
        )

    async def get_source_link_result(self, path: str, filename: str) -> DownloadResult:
        """
        外链下载

        根据 policy.is_private 和 policy.base_url 决定：
        - 公有 + 有 base_url → 302 重定向到 base_url/relative_path
        - 私有或无 base_url → 代理输出文件内容
        """
        is_private = self._policy.is_private
        base_url = self._policy.base_url

        if not is_private and base_url:
            relative_path = self.get_relative_path(path)
            redirect_url = f"{base_url}/{relative_path}"
            return DownloadResult(
                kind=DownloadKind.REDIRECT_URL,
                redirect_url=redirect_url,
                filename=filename,
            )

        return DownloadResult(
            kind=DownloadKind.FILE_PATH,
            file_path=path,
            filename=filename,
        )

    # ==================== 回收站 ====================

    async def move_to_trash(
        self,
        source_path: str,
        user_id: UUID,
        entry_id: UUID,
    ) -> str | None:
        """
        将文件移动到回收站

        :param source_path: 源文件完整路径
        :param user_id: 用户UUID
        :param entry_id: 文件条目UUID
        :return: 回收站中的文件路径
        :raises StorageFileNotFoundError: 源文件不存在时抛出
        """
        if not await self.exists(source_path):
            raise StorageFileNotFoundError(f"源文件不存在: {source_path}")

        trash_dir = await self.ensure_trash_directory(user_id)
        source_filename = Path(source_path).name
        trash_filename = f"{entry_id}_{source_filename}"
        trash_path = trash_dir / trash_filename

        try:
            await aiofiles.os.rename(source_path, str(trash_path))
            l.info(f"文件已移动到回收站: {source_path} -> {trash_path}")
            await self._cleanup_empty_parents(source_path)
            return str(trash_path)
        except OSError as e:
            raise StorageException(f"移动文件到回收站失败: {e}")

    async def restore_from_trash(self, trash_path: str, restore_path: str) -> None:
        """
        从回收站恢复文件

        :param trash_path: 回收站中的文件路径
        :param restore_path: 恢复目标路径
        :raises StorageFileNotFoundError: 回收站文件不存在时抛出
        """
        if not await self.exists(trash_path):
            raise StorageFileNotFoundError(f"回收站文件不存在: {trash_path}")

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

    # ==================== 内部方法 ====================

    async def _cleanup_empty_parents(self, file_path: str) -> None:
        """从被删文件的父目录开始，向上逐级删除空目录"""
        current = Path(file_path).parent

        while current != self._base_path and str(current).startswith(str(self._base_path)):
            if current.name == '.trash':
                break
            try:
                entries = await aiofiles.os.listdir(str(current))
                if entries:
                    break
                await aiofiles.os.rmdir(str(current))
                l.debug(f"已清理空目录: {current}")
                current = current.parent
            except OSError as e:
                l.debug(f"清理空目录失败（忽略）: {current}: {e}")
                break


# 向后兼容别名（Phase 5 删除）
LocalStorageService = LocalStorageDriver
