"""存储服务工厂函数"""
from sqlmodels.policy import Policy, PolicyType

from .local_storage import LocalStorageService
from .protocol import StorageHandler
from .s3_storage import S3StorageService


def create_storage_service(policy: Policy) -> StorageHandler:
    """
    根据 Policy 类型创建对应的存储服务实例

    :param policy: 存储策略
    :return: 实现 StorageHandler 协议的存储服务实例
    :raises ValueError: 未知的策略类型
    """
    if policy.type == PolicyType.LOCAL:
        return LocalStorageService(policy)
    elif policy.type == PolicyType.S3:
        return S3StorageService.from_policy(policy)
    raise ValueError(f"未知策略类型: {policy.type}")
