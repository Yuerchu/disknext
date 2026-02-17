"""
WebDAV 认证缓存

缓存 HTTP Basic Auth 的认证结果，避免每次请求都查库 + Argon2 验证。
支持 Redis（首选）和内存缓存（降级）两种存储后端。
"""
import hashlib
from typing import ClassVar
from uuid import UUID

from cachetools import TTLCache
from loguru import logger as l

from . import RedisManager

_AUTH_TTL: int = 300
"""认证缓存 TTL（秒），5 分钟"""


class WebDAVAuthCache:
    """
    WebDAV 认证结果缓存

    缓存键格式: webdav_auth:{email}/{account_name}:{sha256(password)}
    缓存值格式: {user_id}:{webdav_id}

    密码的 SHA256 作为缓存键的一部分，密码变更后旧缓存自然 miss。
    """

    _memory_cache: ClassVar[TTLCache[str, str]] = TTLCache(maxsize=10000, ttl=_AUTH_TTL)
    """内存缓存降级方案"""

    @classmethod
    def _build_key(cls, email: str, account_name: str, password: str) -> str:
        """构建缓存键"""
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()[:16]
        return f"webdav_auth:{email}/{account_name}:{pwd_hash}"

    @classmethod
    async def get(
        cls,
        email: str,
        account_name: str,
        password: str,
    ) -> tuple[UUID, int] | None:
        """
        查询缓存中的认证结果。

        :param email: 用户邮箱
        :param account_name: WebDAV 账户名
        :param password: 用户提供的明文密码
        :return: (user_id, webdav_id) 或 None（缓存未命中）
        """
        key = cls._build_key(email, account_name, password)

        client = RedisManager.get_client()
        if client is not None:
            value = await client.get(key)
            if value is not None:
                raw = value.decode() if isinstance(value, bytes) else value
                user_id_str, webdav_id_str = raw.split(":", 1)
                return UUID(user_id_str), int(webdav_id_str)
        else:
            raw = cls._memory_cache.get(key)
            if raw is not None:
                user_id_str, webdav_id_str = raw.split(":", 1)
                return UUID(user_id_str), int(webdav_id_str)

        return None

    @classmethod
    async def set(
        cls,
        email: str,
        account_name: str,
        password: str,
        user_id: UUID,
        webdav_id: int,
    ) -> None:
        """
        写入认证结果到缓存。

        :param email: 用户邮箱
        :param account_name: WebDAV 账户名
        :param password: 用户提供的明文密码
        :param user_id: 用户UUID
        :param webdav_id: WebDAV 账户ID
        """
        key = cls._build_key(email, account_name, password)
        value = f"{user_id}:{webdav_id}"

        client = RedisManager.get_client()
        if client is not None:
            await client.set(key, value, ex=_AUTH_TTL)
        else:
            cls._memory_cache[key] = value

    @classmethod
    async def invalidate_account(cls, user_id: UUID, account_name: str) -> None:
        """
        失效指定账户的所有缓存。

        由于缓存键包含 password hash，无法精确删除，
        Redis 端使用 pattern scan 删除，内存端清空全部。

        :param user_id: 用户UUID
        :param account_name: WebDAV 账户名
        """
        client = RedisManager.get_client()
        if client is not None:
            pattern = f"webdav_auth:*/{account_name}:*"
            cursor: int = 0
            while True:
                cursor, keys = await client.scan(cursor, match=pattern, count=100)
                if keys:
                    await client.delete(*keys)
                if cursor == 0:
                    break
        else:
            # 内存缓存无法按 pattern 删除，清除所有含该账户名的条目
            keys_to_delete = [
                k for k in cls._memory_cache
                if f"/{account_name}:" in k
            ]
            for k in keys_to_delete:
                cls._memory_cache.pop(k, None)

        l.debug(f"已清除 WebDAV 认证缓存: user={user_id}, account={account_name}")
