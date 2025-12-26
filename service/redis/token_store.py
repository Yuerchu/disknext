"""
一次性令牌状态存储

支持 Redis（首选）和内存缓存（降级）两种存储后端。
"""
from datetime import timedelta
from typing import ClassVar

from cachetools import TTLCache
from loguru import logger as l

from . import RedisManager


class TokenStore:
    """
    一次性令牌存储管理器

    根据 Redis 可用性自动选择存储后端：
    - Redis 可用：使用 Redis（支持分布式部署）
    - Redis 不可用：使用内存缓存（仅单实例）
    """

    _memory_cache: ClassVar[TTLCache[str, bool]] = TTLCache(maxsize=10000, ttl=3600)
    """内存缓存降级方案"""

    @classmethod
    async def mark_used(cls, jti: str, ttl: timedelta | int) -> bool:
        """
        标记令牌为已使用（原子操作）。

        :param jti: 令牌唯一标识符（JWT ID）
        :param ttl: 过期时间
        :return: True 表示首次标记成功（可以使用），False 表示已被使用
        """
        ttl_seconds = int(ttl.total_seconds()) if isinstance(ttl, timedelta) else ttl
        client = RedisManager.get_client()

        if client is not None:
            # 使用 Redis SETNX 原子操作
            key = f"download_token:{jti}"
            result = await client.set(key, "1", nx=True, ex=ttl_seconds)
            return result is not None
        else:
            # 降级使用内存缓存
            if jti in cls._memory_cache:
                return False
            cls._memory_cache[jti] = True
            return True

    @classmethod
    async def is_used(cls, jti: str) -> bool:
        """
        检查令牌是否已被使用。

        :param jti: 令牌唯一标识符
        :return: True 表示已被使用
        """
        client = RedisManager.get_client()

        if client is not None:
            key = f"download_token:{jti}"
            return await client.exists(key) > 0
        else:
            return jti in cls._memory_cache
