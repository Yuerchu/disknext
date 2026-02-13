"""
WebAuthn Challenge 一次性存储

支持 Redis（首选，使用 GETDEL 原子操作）和内存 TTLCache（降级）。
Challenge 存储后 5 分钟过期，取出即删除（防重放）。
"""
from typing import ClassVar

from cachetools import TTLCache
from loguru import logger as l

from . import RedisManager

# Challenge 过期时间（秒）
_CHALLENGE_TTL: int = 300


class ChallengeStore:
    """
    WebAuthn Challenge 一次性存储管理器

    根据 Redis 可用性自动选择存储后端：
    - Redis 可用：使用 Redis GETDEL 原子操作
    - Redis 不可用：使用内存 TTLCache（仅单实例）

    Key 约定：
    - 注册: ``reg:{user_id}``
    - 登录: ``auth:{challenge_token}``
    """

    _memory_cache: ClassVar[TTLCache[str, bytes]] = TTLCache(
        maxsize=10000,
        ttl=_CHALLENGE_TTL,
    )
    """内存缓存降级方案"""

    @classmethod
    async def store(cls, key: str, challenge: bytes) -> None:
        """
        存储 challenge，TTL 5 分钟。

        :param key: 存储键（如 ``reg:{user_id}`` 或 ``auth:{token}``）
        :param challenge: challenge 字节数据
        """
        client = RedisManager.get_client()

        if client is not None:
            redis_key = f"webauthn_challenge:{key}"
            await client.set(redis_key, challenge, ex=_CHALLENGE_TTL)
        else:
            cls._memory_cache[key] = challenge

    @classmethod
    async def retrieve_and_delete(cls, key: str) -> bytes | None:
        """
        一次性取出并删除 challenge（防重放）。

        :param key: 存储键
        :return: challenge 字节数据，过期或不存在时返回 None
        """
        client = RedisManager.get_client()

        if client is not None:
            redis_key = f"webauthn_challenge:{key}"
            result: bytes | None = await client.getdel(redis_key)
            return result
        else:
            return cls._memory_cache.pop(key, None)
