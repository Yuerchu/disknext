"""
存储基础设施模块

提供文件存储的底层适配器和工具：
- 本地存储服务
- S3 存储服务
- 命名规则解析器
- 存储异常定义
"""
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
from .local_storage import LocalStorageService
from .migrate import migrate_file_with_task, migrate_directory_files
from .naming_rule import NamingContext, NamingRuleParser
from .s3_storage import S3StorageService
