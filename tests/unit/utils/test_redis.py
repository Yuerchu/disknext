"""
Redis 工具类单元测试

测试 UserBanStore、TokenStore、ChallengeStore、ServerConfigCache、WebDAVAuthCache
的核心逻辑，基于真实 Redis 实例（由 conftest 管理连接和 flushdb 隔离）。
"""
from datetime import timedelta
from uuid import uuid4

import pytest

from utils.redis.user_ban_store import UserBanStore
from utils.redis.token_store import TokenStore
from utils.redis.challenge_store import ChallengeStore
from utils.redis.server_config_cache import ServerConfigCache
from utils.redis.webdav_auth_cache import WebDAVAuthCache


# ==================== UserBanStore ====================

class TestUserBanStore:
    """用户封禁状态存储测试"""

    @pytest.mark.asyncio
    async def test_ban_and_check(self):
        """封禁用户后 is_banned 返回 True"""
        user_id = str(uuid4())
        await UserBanStore.ban(user_id)
        assert await UserBanStore.is_banned(user_id) is True

    @pytest.mark.asyncio
    async def test_not_banned_by_default(self):
        """未封禁的用户 is_banned 返回 False"""
        user_id = str(uuid4())
        assert await UserBanStore.is_banned(user_id) is False

    @pytest.mark.asyncio
    async def test_unban(self):
        """解封后 is_banned 返回 False"""
        user_id = str(uuid4())
        await UserBanStore.ban(user_id)
        assert await UserBanStore.is_banned(user_id) is True

        await UserBanStore.unban(user_id)
        assert await UserBanStore.is_banned(user_id) is False

    @pytest.mark.asyncio
    async def test_unban_nonexistent(self):
        """解封不存在的用户不报错"""
        user_id = str(uuid4())
        await UserBanStore.unban(user_id)  # 不应该抛异常

    @pytest.mark.asyncio
    async def test_ban_idempotent(self):
        """重复封禁同一用户是幂等的"""
        user_id = str(uuid4())
        await UserBanStore.ban(user_id)
        await UserBanStore.ban(user_id)
        assert await UserBanStore.is_banned(user_id) is True

    @pytest.mark.asyncio
    async def test_ban_different_users_independent(self):
        """不同用户的封禁状态互相独立"""
        user_a = str(uuid4())
        user_b = str(uuid4())
        await UserBanStore.ban(user_a)

        assert await UserBanStore.is_banned(user_a) is True
        assert await UserBanStore.is_banned(user_b) is False


# ==================== TokenStore ====================

class TestTokenStore:
    """一次性令牌存储测试"""

    @pytest.mark.asyncio
    async def test_mark_used_first_time(self):
        """首次标记返回 True"""
        jti = str(uuid4())
        result = await TokenStore.mark_used(jti, ttl=60)
        assert result is True

    @pytest.mark.asyncio
    async def test_mark_used_second_time(self):
        """重复标记返回 False（SETNX 原子性）"""
        jti = str(uuid4())
        first = await TokenStore.mark_used(jti, ttl=60)
        second = await TokenStore.mark_used(jti, ttl=60)
        assert first is True
        assert second is False

    @pytest.mark.asyncio
    async def test_is_used_after_mark(self):
        """标记后 is_used 返回 True"""
        jti = str(uuid4())
        await TokenStore.mark_used(jti, ttl=60)
        assert await TokenStore.is_used(jti) is True

    @pytest.mark.asyncio
    async def test_is_used_not_marked(self):
        """未标记的令牌 is_used 返回 False"""
        jti = str(uuid4())
        assert await TokenStore.is_used(jti) is False

    @pytest.mark.asyncio
    async def test_mark_used_with_timedelta(self):
        """支持 timedelta 作为 TTL"""
        jti = str(uuid4())
        result = await TokenStore.mark_used(jti, ttl=timedelta(minutes=5))
        assert result is True
        assert await TokenStore.is_used(jti) is True

    @pytest.mark.asyncio
    async def test_different_tokens_independent(self):
        """不同令牌的使用状态互相独立"""
        jti_a = str(uuid4())
        jti_b = str(uuid4())
        await TokenStore.mark_used(jti_a, ttl=60)

        assert await TokenStore.is_used(jti_a) is True
        assert await TokenStore.is_used(jti_b) is False


# ==================== ChallengeStore ====================

class TestChallengeStore:
    """WebAuthn Challenge 一次性存储测试"""

    @pytest.mark.asyncio
    async def test_store_and_retrieve(self):
        """存储后能成功取出"""
        key = f"reg:{uuid4()}"
        challenge = b"test_challenge_bytes"

        await ChallengeStore.store(key, challenge)
        result = await ChallengeStore.retrieve_and_delete(key)
        assert result == challenge

    @pytest.mark.asyncio
    async def test_retrieve_deletes(self):
        """取出后自动删除（防重放）"""
        key = f"auth:{uuid4()}"
        challenge = b"one_time_challenge"

        await ChallengeStore.store(key, challenge)

        first = await ChallengeStore.retrieve_and_delete(key)
        assert first == challenge

        second = await ChallengeStore.retrieve_and_delete(key)
        assert second is None

    @pytest.mark.asyncio
    async def test_retrieve_nonexistent(self):
        """取不存在的 key 返回 None"""
        result = await ChallengeStore.retrieve_and_delete(f"nonexistent:{uuid4()}")
        assert result is None

    @pytest.mark.asyncio
    async def test_store_overwrites(self):
        """重复存储同一个 key 覆盖旧值"""
        key = f"reg:{uuid4()}"
        await ChallengeStore.store(key, b"old_challenge")
        await ChallengeStore.store(key, b"new_challenge")

        result = await ChallengeStore.retrieve_and_delete(key)
        assert result == b"new_challenge"

    @pytest.mark.asyncio
    async def test_different_keys_independent(self):
        """不同 key 的 challenge 互相独立"""
        key_a = f"reg:{uuid4()}"
        key_b = f"auth:{uuid4()}"

        await ChallengeStore.store(key_a, b"challenge_a")
        await ChallengeStore.store(key_b, b"challenge_b")

        assert await ChallengeStore.retrieve_and_delete(key_a) == b"challenge_a"
        assert await ChallengeStore.retrieve_and_delete(key_b) == b"challenge_b"


# ==================== ServerConfigCache ====================

class TestServerConfigCache:
    """ServerConfig 缓存测试"""

    @pytest.mark.asyncio
    async def test_get_empty_cache(self):
        """缓存为空时返回 None"""
        result = await ServerConfigCache.get()
        assert result is None

    @pytest.mark.asyncio
    async def test_set_and_get(self):
        """设置后能取出"""
        from sqlmodels.server_config import ServerConfig

        config = ServerConfig(
            id=1,
            site_name="Test Site",
            site_url="http://localhost:8000",
            site_title="Test",
            home_view_method="list",
            share_view_method="list",
        )
        await ServerConfigCache.set(config)

        cached = await ServerConfigCache.get()
        assert cached is not None
        assert cached.site_name == "Test Site"
        assert cached.site_url == "http://localhost:8000"

    @pytest.mark.asyncio
    async def test_invalidate(self):
        """清除缓存后返回 None"""
        from sqlmodels.server_config import ServerConfig

        config = ServerConfig(
            id=1,
            site_name="Test",
            site_url="http://localhost",
            site_title="T",
            home_view_method="list",
            share_view_method="list",
        )
        await ServerConfigCache.set(config)
        assert await ServerConfigCache.get() is not None

        await ServerConfigCache.invalidate()
        assert await ServerConfigCache.get() is None

    @pytest.mark.asyncio
    async def test_invalidate_empty_no_error(self):
        """清除不存在的缓存不报错"""
        await ServerConfigCache.invalidate()  # 不应该抛异常


# ==================== WebDAVAuthCache ====================

class TestWebDAVAuthCache:
    """WebDAV 认证缓存测试"""

    @pytest.mark.asyncio
    async def test_set_and_get(self):
        """设置认证缓存后能取出"""
        email = "test@example.com"
        account = "default"
        password = "mypassword"
        user_id = uuid4()
        webdav_id = 42

        await WebDAVAuthCache.set(email, account, password, user_id, webdav_id)
        result = await WebDAVAuthCache.get(email, account, password)

        assert result is not None
        assert result[0] == user_id
        assert result[1] == webdav_id

    @pytest.mark.asyncio
    async def test_get_miss(self):
        """缓存未命中返回 None"""
        result = await WebDAVAuthCache.get("nobody@example.com", "acc", "pwd")
        assert result is None

    @pytest.mark.asyncio
    async def test_wrong_password_misses(self):
        """密码不同则缓存 miss（密码 hash 作为 key 的一部分）"""
        email = "test@example.com"
        account = "default"
        user_id = uuid4()

        await WebDAVAuthCache.set(email, account, "correct_password", user_id, 1)

        result = await WebDAVAuthCache.get(email, account, "wrong_password")
        assert result is None

    @pytest.mark.asyncio
    async def test_invalidate_account(self):
        """失效指定账户的所有缓存"""
        email = "test@example.com"
        account = "work"
        user_id = uuid4()

        await WebDAVAuthCache.set(email, account, "pwd1", user_id, 1)
        await WebDAVAuthCache.set(email, account, "pwd2", user_id, 2)

        await WebDAVAuthCache.invalidate_account(user_id, account)

        assert await WebDAVAuthCache.get(email, account, "pwd1") is None
        assert await WebDAVAuthCache.get(email, account, "pwd2") is None

    @pytest.mark.asyncio
    async def test_build_key_consistency(self):
        """相同输入产生相同的缓存键"""
        key1 = WebDAVAuthCache._build_key("a@b.com", "acc", "pwd")
        key2 = WebDAVAuthCache._build_key("a@b.com", "acc", "pwd")
        assert key1 == key2

    @pytest.mark.asyncio
    async def test_build_key_different_for_different_input(self):
        """不同输入产生不同的缓存键"""
        key1 = WebDAVAuthCache._build_key("a@b.com", "acc", "pwd1")
        key2 = WebDAVAuthCache._build_key("a@b.com", "acc", "pwd2")
        assert key1 != key2
