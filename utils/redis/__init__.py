"""
Redis 服务模块

提供 Redis 异步客户端的生命周期管理。
DiskNext 强制要求 Redis，未配置或连接失败均启动失败。
"""
import asyncio
from typing import ClassVar

import redis.asyncio as aioredis
from loguru import logger as l
from redis.exceptions import RedisError

from utils.conf import appmeta


_NOT_INITIALIZED_MSG = "Redis 客户端未初始化，请先调用 RedisManager.connect()"


class RedisManager:
    """
    Redis 连接管理器

    使用 ClassVar 管理全局单例客户端。连接失败直接 raise，
    调用方不需要做可用性判断。
    """

    _client: ClassVar[aioredis.Redis | None] = None
    """Redis 客户端实例"""

    _is_initialized: ClassVar[bool] = False
    """是否已完成初始化"""

    @classmethod
    def get_client(cls) -> aioredis.Redis:
        """
        获取 Redis 客户端实例。

        :return: Redis 客户端
        :raises RuntimeError: 未初始化时抛出
        """
        if not cls._is_initialized or cls._client is None:
            raise RuntimeError(_NOT_INITIALIZED_MSG)
        return cls._client

    @classmethod
    async def connect(cls) -> None:
        """
        连接 Redis 服务器。

        在应用启动时调用。连接失败直接抛出 ConnectionError 让 FastAPI 启动失败。

        :raises ConnectionError: Redis 连接失败
        """
        if cls._is_initialized:
            l.warning("Redis 客户端已初始化，跳过重复初始化")
            return

        try:
            cls._client = aioredis.from_url(
                appmeta.redis_url,
                protocol=3,
                decode_responses=False,
            )
            await cls._client.ping()
            cls._is_initialized = True
            l.info(f"Redis 连接成功: {appmeta.redis_url}")

        except (RedisError, asyncio.TimeoutError, OSError) as e:
            cls._client = None
            cls._is_initialized = False
            raise ConnectionError(f"无法连接到 Redis 服务器: {e}") from e

    @classmethod
    async def disconnect(cls) -> None:
        """
        断开 Redis 连接。

        在应用关闭时调用。
        """
        if cls._client is not None:
            await cls._client.aclose()
            cls._client = None
            cls._is_initialized = False
            l.info("Redis 连接已关闭")
