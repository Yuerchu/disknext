"""存储驱动工厂函数"""
from typing import TYPE_CHECKING

from .base import StorageDriver
from .local_storage import LocalStorageDriver
from .s3_storage import S3StorageDriver

if TYPE_CHECKING:
    from sqlmodels.policy import Policy


def create_storage_driver(policy: 'Policy') -> StorageDriver:
    """
    根据 Policy 类型创建对应的存储驱动实例

    :param policy: 存储策略
    :return: StorageDriver 子类实例
    :raises ValueError: 未知的策略类型
    """
    # PolicyType 是 StrEnum，直接与字符串比较
    if policy.type == "local":
        return LocalStorageDriver(policy)
    elif policy.type == "s3":
        return S3StorageDriver(policy)
    raise ValueError(f"未知策略类型: {policy.type}")


# 向后兼容别名（Phase 5 删除）
create_storage_service = create_storage_driver
