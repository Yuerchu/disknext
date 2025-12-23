"""
存储服务异常定义

定义存储操作相关的异常类型，用于精确的错误处理和诊断。
"""


class StorageException(Exception):
    """存储服务基础异常"""
    pass


class DirectoryCreationError(StorageException):
    """目录创建失败"""
    pass


class StorageFileNotFoundError(StorageException):
    """文件不存在"""
    pass


class FileWriteError(StorageException):
    """文件写入失败"""
    pass


class FileReadError(StorageException):
    """文件读取失败"""
    pass


class UploadSessionNotFoundError(StorageException):
    """上传会话不存在"""
    pass


class UploadSessionExpiredError(StorageException):
    """上传会话已过期"""
    pass


class InvalidPathError(StorageException):
    """无效的路径"""
    pass
