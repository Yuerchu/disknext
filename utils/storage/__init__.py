"""
存储基础设施模块

提供文件存储的底层适配器和工具：
- StorageDriver 抽象基类
- LocalStorageDriver / S3StorageDriver 驱动实现
- 命名规则解析器
- 存储异常定义
- 存储驱动工厂函数
"""
from .base import StorageDriver
from .exceptions import (
    DirectoryCreationError,
    FileReadError,
    FileWriteError,
    InvalidPathError,
    S3APIError,
    S3MultipartUploadError,
    StorageException,
    StorageFileNotFoundError,
    UploadSessionExpiredError,
    UploadSessionNotFoundError,
)
from .factory import create_storage_driver, create_storage_service
from .local_storage import LocalStorageDriver, LocalStorageService
from .migrate import migrate_directory_files, migrate_file_with_task
from .models import ChunkResult, DownloadKind, DownloadResult, UploadContext
from .naming_rule import NamingContext, NamingRuleParser
from .s3_storage import S3StorageDriver, S3StorageService
