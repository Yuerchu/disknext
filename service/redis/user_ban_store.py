"""
用户封禁状态存储

用于 JWT 模式下的即时封禁生效。
支持 Redis（首选）和内存缓存（降级）两种存储后端。
"""
from typing import ClassVar

from cachetools import TTLCache
from loguru import logger as l

from . import RedisManager

# access_token 有效期（秒）
_BAN_TTL: int = 3600


class UserBanStore:
    """
    用户封禁状态存储

    管理员封禁用户时调用 ban()，jwt_required 每次请求调用 is_banned() 检查。
    TTL 与 access_token 有效期一致（1h），过期后旧 token 自然失效，无需继续记录。
    """

    _memory_cache: ClassVar[TTLCache[str, bool]] = TTLCache(maxsize=10000, ttl=_BAN_TTL)
    """内存缓存降级方案"""

    @classmethod
    async def ban(cls, user_id: str) -> None:
        """
        标记用户为已封禁。

        :param user_id: 用户 UUID 字符串
        """
        client = RedisManager.get_client()
        if client is not None:
            key = f"user_ban:{user_id}"
            await client.set(key, "1", ex=_BAN_TTL)
        else:
            cls._memory_cache[user_id] = True
        l.info(f"用户 {user_id} 已加入封禁黑名单")

    @classmethod
    async def unban(cls, user_id: str) -> None:
        """
        移除用户封禁标记（解封时调用）。

        :param user_id: 用户 UUID 字符串
        """
        client = RedisManager.get_client()
        if client is not None:
            key = f"user_ban:{user_id}"
            await client.delete(key)
        else:
            cls._memory_cache.pop(user_id, None)
        l.info(f"用户 {user_id} 已从封禁黑名单移除")

    @classmethod
    async def is_banned(cls, user_id: str) -> bool:
        """
        检查用户是否在封禁黑名单中。

        :param user_id: 用户 UUID 字符串
        :return: True 表示已封禁
        """
        client = RedisManager.get_client()
        if client is not None:
            key = f"user_ban:{user_id}"
            return await client.exists(key) > 0
        else:
            return user_id in cls._memory_cache
