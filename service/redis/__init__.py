"""
Redis 服务模块

提供 Redis 异步客户端的生命周期管理。
通过环境变量配置连接参数，未配置时不初始化客户端。
"""
from typing import ClassVar

import redis.asyncio as aioredis
from loguru import logger as l

from utils.conf import appmeta


class RedisManager:
    """
    Redis 连接管理器

    使用 ClassVar 管理全局单例客户端。
    """

    _client: ClassVar[aioredis.Redis | None] = None
    """Redis 客户端实例"""

    _is_available: ClassVar[bool] = False
    """Redis 是否可用"""

    @classmethod
    def is_configured(cls) -> bool:
        """检查是否配置了 Redis"""
        return appmeta.redis_url is not None

    @classmethod
    def is_available(cls) -> bool:
        """检查 Redis 是否可用"""
        return cls._is_available

    @classmethod
    def get_client(cls) -> aioredis.Redis | None:
        """
        获取 Redis 客户端实例。

        :return: Redis 客户端，未配置或连接失败时返回 None
        """
        return cls._client if cls._is_available else None

    @classmethod
    async def connect(cls) -> None:
        """
        连接 Redis 服务器。

        在应用启动时调用，如果未配置 Redis 则跳过。
        """
        if not cls.is_configured():
            l.info("未配置 REDIS_URL，跳过 Redis 连接")
            return

        try:
            cls._client = aioredis.Redis(
                host=appmeta.redis_url,
                port=appmeta.redis_port,
                password=appmeta.redis_password,
                db=appmeta.redis_db,
                protocol=appmeta.redis_protocol,
            )

            # 测试连接
            await cls._client.ping()
            cls._is_available = True
            l.info(f"Redis 连接成功: {appmeta.redis_url}:{appmeta.redis_port}")

        except Exception as e:
            l.warning(f"Redis 连接失败，将使用内存缓存作为降级方案: {e}")
            cls._client = None
            cls._is_available = False

    @classmethod
    async def disconnect(cls) -> None:
        """
        断开 Redis 连接。

        在应用关闭时调用。
        """
        if cls._client is not None:
            await cls._client.close()
            cls._client = None
            cls._is_available = False
            l.info("Redis 连接已关闭")
