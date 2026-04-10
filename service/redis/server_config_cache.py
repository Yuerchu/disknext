"""
ServerConfig Redis 缓存

使用 Redis 存储 ServerConfig 序列化数据，减少数据库查询。
"""
from loguru import logger as l

from . import RedisManager


_CACHE_KEY = "server_config:1"
_TTL = 3600  # 1 小时


class ServerConfigCache:
    """
    ServerConfig Redis 缓存管理器

    序列化使用 model_dump_json / model_validate_json。
    Redis 不可用时不缓存，每次请求直接查询数据库。
    """

    @classmethod
    async def get(cls) -> 'ServerConfig | None':
        """
        从 Redis 获取 ServerConfig。

        :return: 缓存命中时返回 ServerConfig 实例，否则返回 None
        """
        from sqlmodels.server_config import ServerConfig

        client = RedisManager.get_client()
        if client is None:
            return None

        raw: bytes | None = await client.get(_CACHE_KEY)
        if raw is None:
            return None

        return ServerConfig.model_validate_json(raw)

    @classmethod
    async def set(cls, config: 'ServerConfig') -> None:
        """
        将 ServerConfig 写入 Redis。

        :param config: 要缓存的配置实例
        """
        client = RedisManager.get_client()
        if client is None:
            return

        json_str: str = config.model_dump_json()
        await client.set(_CACHE_KEY, json_str, ex=_TTL)

    @classmethod
    async def invalidate(cls) -> None:
        """
        清除 ServerConfig 缓存。

        在配置更新后调用，确保下次读取获取最新数据。
        """
        client = RedisManager.get_client()
        if client is None:
            return

        await client.delete(_CACHE_KEY)
        l.debug("ServerConfig 缓存已清除")
