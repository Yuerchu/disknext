"""
存储处理器协议

定义所有存储后端（LOCAL、S3 等）必须实现的统一接口。
路由层通过 ``create_storage_service()`` 工厂获取 ``StorageHandler`` 实例，
无需关心底层存储类型。
"""
from typing import Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class StorageHandler(Protocol):
    """存储后端统一协议"""

    async def write(self, path: str, content: bytes) -> int:
        """
        写入文件内容

        :param path: 存储路径
        :param content: 文件内容
        :return: 写入的字节数
        """
        ...

    async def write_chunk(self, path: str, content: bytes, offset: int) -> int:
        """
        写入文件分片

        :param path: 存储路径
        :param content: 分片内容
        :param offset: 写入偏移量
        :return: 写入的字节数
        """
        ...

    async def read(self, path: str) -> bytes:
        """
        读取完整文件

        :param path: 存储路径
        :return: 文件内容
        """
        ...

    async def delete(self, path: str) -> None:
        """
        删除文件

        :param path: 存储路径
        """
        ...

    async def exists(self, path: str) -> bool:
        """
        检查文件是否存在

        :param path: 存储路径
        :return: 是否存在
        """
        ...

    async def create_empty(self, path: str) -> None:
        """
        创建空白文件

        :param path: 存储路径
        """
        ...

    async def generate_path(
        self,
        user_id: UUID,
        original_filename: str,
    ) -> tuple[str, str, str]:
        """
        根据命名规则生成文件存储路径

        :param user_id: 用户UUID
        :param original_filename: 原始文件名
        :return: (相对目录路径, 存储文件名, 完整存储路径)
        """
        ...

    def get_relative_path(self, full_path: str) -> str:
        """
        获取相对于存储根目录的相对路径

        :param full_path: 完整路径
        :return: 相对路径
        """
        ...
