"""
存储服务模块

提供文件存储相关的服务，包括：
- 本地存储服务
- 命名规则解析器
- 存储异常定义
"""
from .exceptions import (
    DirectoryCreationError,
    FileReadError,
    FileWriteError,
    InvalidPathError,
    StorageException,
    StorageFileNotFoundError,
    UploadSessionExpiredError,
    UploadSessionNotFoundError,
)
from .local_storage import LocalStorageService
from .naming_rule import NamingContext, NamingRuleParser
from .object import (
    adjust_user_storage,
    copy_object_recursive,
    delete_object_recursive,
    permanently_delete_objects,
    restore_objects,
    soft_delete_objects,
)