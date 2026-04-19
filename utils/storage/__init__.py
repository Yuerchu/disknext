"""
存储基础设施模块

提供文件存储的底层适配器和工具：
- 本地存储服务
- S3 存储服务
- 命名规则解析器
- 存储异常定义
- 存储服务工厂函数
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
from .factory import create_storage_service
from .local_storage import LocalStorageService
from .naming_rule import NamingContext, NamingRuleParser
from .protocol import StorageHandler
from .s3_storage import S3StorageService
