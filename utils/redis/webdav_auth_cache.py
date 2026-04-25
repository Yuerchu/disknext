"""
WebDAV 认证缓存

缓存 HTTP Basic Auth 的认证结果，避免每次请求都查库 + Argon2 验证。
"""
import hashlib
from uuid import UUID

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

        value = await client.get(key)
        if value is None:
            return None

        raw = value.decode() if isinstance(value, bytes) else value
        user_id_str, webdav_id_str = raw.split(":", 1)
        return UUID(user_id_str), int(webdav_id_str)

    @classmethod
    async def set(
        cls,
        email: str,
        account_name: str,
        password: str,
        user_id: UUID,
        webdav_id: UUID,
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
        await client.set(key, value, ex=_AUTH_TTL)

    @classmethod
    async def invalidate_account(cls, user_id: UUID, account_name: str) -> None:
        """
        失效指定账户的所有缓存。

        由于缓存键包含 password hash，无法精确删除，使用 pattern scan 删除。

        :param user_id: 用户UUID
        :param account_name: WebDAV 账户名
        """
        client = RedisManager.get_client()
        pattern = f"webdav_auth:*/{account_name}:*"
        cursor: int = 0
        while True:
            cursor, keys = await client.scan(cursor, match=pattern, count=100)
            if keys:
                await client.delete(*keys)
            if cursor == 0:
                break

        l.debug(f"已清除 WebDAV 认证缓存: user={user_id}, account={account_name}")
