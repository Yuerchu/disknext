"""
存储驱动抽象基类

所有存储后端（Local、S3 等）继承此基类，实现/覆盖抽象方法。
路由层通过 ``create_storage_driver()`` 工厂获取 ``StorageDriver`` 实例，
无需关心底层存储类型。

基类提供：
- ``generate_path()``：基于 NamingRuleParser 的共享路径生成逻辑
- 能力声明属性的默认值
- ``generate_presigned_url()`` 等可选方法的默认实现（raise NotImplementedError）

子类必须实现所有 ``@abstractmethod`` 方法。
"""
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from uuid import UUID

from .models import ChunkResult, DownloadResult, UploadContext
from .naming_rule import NamingContext, NamingRuleParser

if TYPE_CHECKING:
    from sqlmodels.policy import Policy


class StorageDriver(ABC):
    """存储驱动抽象基类"""

    def __init__(self, policy: 'Policy') -> None:
        self._policy = policy

    @property
    def policy(self) -> 'Policy':
        """关联的存储策略"""
        return self._policy

    # ==================== 共享实现 ====================

    async def generate_path(
        self,
        user_id: UUID,
        original_filename: str,
    ) -> tuple[str, str, str]:
        """
        根据命名规则生成文件存储路径

        使用 ``NamingRuleParser`` 解析 ``policy.dir_name_rule`` 和 ``policy.file_name_rule``，
        然后调用 ``_assemble_path()`` 由子类决定如何拼接最终路径。

        :param user_id: 用户UUID
        :param original_filename: 原始文件名
        :return: (相对目录路径, 存储文件名, 完整存储路径)
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

        full_path = await self._assemble_path(dir_path, storage_name)
        return dir_path, storage_name, full_path

    @abstractmethod
    async def _assemble_path(self, dir_path: str, storage_name: str) -> str:
        """
        子类实现：将目录路径和文件名组装为完整存储路径

        Local 使用 os.path.join(base_path, dir_path, storage_name) 并创建目录。
        S3 使用 / 拼接，无需创建目录。

        :param dir_path: 相对目录路径（可能为空）
        :param storage_name: 存储文件名
        :return: 完整存储路径
        """
        ...

    # ==================== 核心 I/O（抽象） ====================

    @abstractmethod
    async def write(self, path: str, content: bytes) -> int:
        """
        写入文件内容

        :param path: 存储路径
        :param content: 文件内容
        :return: 写入的字节数
        """
        ...

    @abstractmethod
    async def read(self, path: str) -> bytes:
        """
        读取完整文件

        :param path: 存储路径
        :return: 文件内容
        """
        ...

    @abstractmethod
    async def delete(self, path: str) -> None:
        """
        删除文件

        :param path: 存储路径
        """
        ...

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """
        检查文件是否存在

        :param path: 存储路径
        :return: 是否存在
        """
        ...

    @abstractmethod
    async def get_size(self, path: str) -> int:
        """
        获取文件大小

        :param path: 存储路径
        :return: 文件大小（字节）
        """
        ...

    @abstractmethod
    async def create_empty(self, path: str) -> None:
        """
        创建空白文件

        :param path: 存储路径
        """
        ...

    @abstractmethod
    def get_relative_path(self, full_path: str) -> str:
        """
        获取相对于存储根目录的相对路径

        :param full_path: 完整路径
        :return: 相对路径
        """
        ...

    # ==================== 分片上传生命周期（抽象） ====================

    @abstractmethod
    async def init_upload(
        self,
        path: str,
        total_size: int,
        chunk_size: int,
        content_type: str = 'application/octet-stream',
    ) -> UploadContext:
        """
        初始化分片上传

        Local：无特殊操作，返回基本 UploadContext。
        S3：多分片时调用 CreateMultipartUpload，填充 s3_upload_id。

        :param path: 存储路径
        :param total_size: 文件总大小
        :param chunk_size: 分片大小
        :param content_type: MIME 类型
        :return: 上传上下文
        """
        ...

    @abstractmethod
    async def upload_chunk(
        self,
        ctx: UploadContext,
        chunk_index: int,
        content: bytes,
    ) -> ChunkResult:
        """
        上传单个分片

        Local：在 offset = chunk_index * chunk_size 处写入。
        S3：调用 UploadPart API，返回 ETag。

        :param ctx: 上传上下文
        :param chunk_index: 分片索引（从 0 开始）
        :param content: 分片内容
        :return: 分片结果
        """
        ...

    @abstractmethod
    async def complete_upload(self, ctx: UploadContext) -> None:
        """
        完成分片上传

        Local：no-op（已在 upload_chunk 中直接写入最终位置）。
        S3：调用 CompleteMultipartUpload API。

        :param ctx: 上传上下文
        """
        ...

    @abstractmethod
    async def abort_upload(self, ctx: UploadContext) -> None:
        """
        取消分片上传

        Local：删除已部分写入的文件。
        S3：调用 AbortMultipartUpload API。

        :param ctx: 上传上下文
        """
        ...

    # ==================== 下载（抽象） ====================

    @abstractmethod
    async def get_download_result(
        self,
        path: str,
        filename: str,
    ) -> DownloadResult:
        """
        获取下载描述符

        Local：返回 FILE_PATH 类型。
        S3：生成预签名 URL，返回 REDIRECT_URL 类型。

        :param path: 存储路径
        :param filename: 下载文件名
        :return: 下载描述符（路由层调用 .to_response() 转为 HTTP 响应）
        """
        ...

    # ==================== 生命周期管理（抽象，允许 no-op） ====================

    @abstractmethod
    async def ensure_base_directory(self) -> None:
        """
        确保存储根目录存在

        Local：创建物理目录。
        S3：no-op。
        """
        ...

    @abstractmethod
    async def move_to_trash(
        self,
        source_path: str,
        user_id: UUID,
        entry_id: UUID,
    ) -> str | None:
        """
        将文件移动到回收站

        Local：移动到 .trash 目录，返回回收站路径。
        S3：直接删除文件，返回 None（S3 无回收站概念）。

        :param source_path: 源文件路径
        :param user_id: 用户UUID
        :param entry_id: 文件条目UUID
        :return: 回收站路径（S3 返回 None）
        """
        ...

    @abstractmethod
    async def restore_from_trash(
        self,
        trash_path: str,
        restore_path: str,
    ) -> None:
        """
        从回收站恢复文件

        Local：移动文件回原位。
        S3：raise NotImplementedError。

        :param trash_path: 回收站路径
        :param restore_path: 恢复目标路径
        """
        ...

    @abstractmethod
    async def empty_trash(self, user_id: UUID) -> int:
        """
        清空用户回收站

        Local：删除 .trash 目录下所有文件。
        S3：返回 0（无回收站）。

        :param user_id: 用户UUID
        :return: 删除的文件数量
        """
        ...

    # ==================== 能力声明（具体默认值，可覆盖） ====================

    @property
    def is_supports_presigned_url(self) -> bool:
        """是否支持预签名 URL 直接下载"""
        return False

    @property
    def is_supports_direct_serving(self) -> bool:
        """是否支持直接输出文件内容（FileResponse）"""
        return False

    # ==================== 可选方法（具体默认实现） ====================

    def generate_presigned_url(
        self,
        key: str,
        method: str = 'GET',
        expires_in: int = 3600,
        filename: str | None = None,
    ) -> str:
        """
        生成预签名 URL（仅 S3 驱动覆盖）

        :raises NotImplementedError: 当前驱动不支持
        """
        raise NotImplementedError("此存储后端不支持预签名 URL")

    async def get_source_link_result(
        self,
        path: str,
        filename: str,
    ) -> DownloadResult:
        """
        获取外链下载描述符

        默认实现等同于 get_download_result()。
        Local 覆盖此方法以根据 is_private / base_url 决定代理或重定向。

        :param path: 存储路径
        :param filename: 文件名
        :return: 下载描述符
        """
        return await self.get_download_result(path, filename)
