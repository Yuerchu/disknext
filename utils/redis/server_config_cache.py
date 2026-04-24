"""
ServerConfig Redis 缓存

使用 Redis 存储 ServerConfig 序列化数据，减少数据库查询。
"""
import orjson
from loguru import logger as l
from redis.exceptions import RedisError

from . import RedisManager


_CACHE_KEY = "server_config:1"
_TTL = 3600  # 1 小时


class ServerConfigCache:
    """
    ServerConfig Redis 缓存管理器

    序列化使用 orjson + model_dump(mode='json') / model_validate。
    属于非关键缓存：Redis 运行时抖动（读/写异常）时仅记日志降级为直查库，
    不中断主流程。启动期 Redis 仍然是强制可用的。
    """

    @classmethod
    async def get(cls) -> 'ServerConfig | None':
        """
        从 Redis 获取 ServerConfig。

        :return: 缓存命中时返回 ServerConfig 实例，未命中或 Redis 抖动时返回 None
        """
        from sqlmodels.server_config import ServerConfig

        try:
            client = RedisManager.get_client()
            raw: bytes | None = await client.get(_CACHE_KEY)
        except RedisError as e:
            l.warning(f"[ServerConfigCache] 读取失败，降级为直查库: {e}")
            return None

        if raw is None:
            return None

        return ServerConfig.model_validate(orjson.loads(raw))

    @classmethod
    async def set(cls, config: 'ServerConfig') -> None:
        """
        将 ServerConfig 写入 Redis。

        :param config: 要缓存的配置实例
        """
        try:
            client = RedisManager.get_client()
            data: bytes = orjson.dumps(config.model_dump(mode='json'))
            await client.set(_CACHE_KEY, data, ex=_TTL)
        except RedisError as e:
            l.warning(f"[ServerConfigCache] 写入失败: {e}")

    @classmethod
    async def invalidate(cls) -> None:
        """
        清除 ServerConfig 缓存。

        在配置更新后调用，确保下次读取获取最新数据。
        """
        try:
            client = RedisManager.get_client()
            await client.delete(_CACHE_KEY)
            l.debug("ServerConfig 缓存已清除")
        except RedisError as e:
            l.warning(f"[ServerConfigCache] 失效失败: {e}")
