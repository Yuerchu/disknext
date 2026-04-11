"""
一次性令牌状态存储

使用 Redis SETNX 实现跨实例的一次性令牌原子标记。
"""
from datetime import timedelta

from . import RedisManager


class TokenStore:
    """
    一次性令牌存储管理器

    使用 Redis SETNX 原子操作确保同一个 jti 只能被标记一次。
    """

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
        key = f"download_token:{jti}"
        result = await client.set(key, "1", nx=True, ex=ttl_seconds)
        return result is not None

    @classmethod
    async def is_used(cls, jti: str) -> bool:
        """
        检查令牌是否已被使用。

        :param jti: 令牌唯一标识符
        :return: True 表示已被使用
        """
        client = RedisManager.get_client()
        key = f"download_token:{jti}"
        return await client.exists(key) > 0
