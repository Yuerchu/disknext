"""
邮箱验证码存储单元测试

测试 VerifyCodeStore 的验证码生成、存储、限流、原子校验逻辑。
基于真实 Redis 实例（由 conftest 管理连接和 flushdb 隔离）。
"""
import pytest

from utils.redis import RedisManager
from utils.redis.verify_code_store import VerifyCodeStore


class TestVerifyCodeStoreGenerate:
    """验证码生成与存储测试"""

    @pytest.mark.asyncio
    async def test_generate_returns_6_digit_code(self):
        """生成的验证码为 6 位数字"""
        code = await VerifyCodeStore.generate_and_store("register", "test@example.com")
        assert len(code) == 6
        assert code.isdigit()

    @pytest.mark.asyncio
    async def test_code_stored_in_redis(self):
        """验证码被存储到 Redis"""
        email = "stored@example.com"
        code = await VerifyCodeStore.generate_and_store("register", email)

        client = RedisManager.get_client()
        stored = await client.get(f"verify_code:register:{email}")
        assert stored is not None
        assert stored.decode() == code

    @pytest.mark.asyncio
    async def test_code_has_ttl(self):
        """验证码有 TTL"""
        email = "ttl@example.com"
        await VerifyCodeStore.generate_and_store("register", email, ttl_minutes=5)

        client = RedisManager.get_client()
        ttl = await client.ttl(f"verify_code:register:{email}")
        assert 0 < ttl <= 300

    @pytest.mark.asyncio
    async def test_different_reasons_isolated(self):
        """不同 reason 的验证码互相隔离（校验时按 reason 区分）"""
        email_a = "isolated_a@example.com"
        email_b = "isolated_b@example.com"
        code_register = await VerifyCodeStore.generate_and_store("register", email_a)
        code_reset = await VerifyCodeStore.generate_and_store("reset", email_b)

        # 用 register 的 code 去校验 reset 应失败（不同 reason 隔离）
        result = await VerifyCodeStore.verify_and_delete("reset", email_a, code_register)
        assert result is False

        # 各自 reason 校验成功
        result_a = await VerifyCodeStore.verify_and_delete("register", email_a, code_register)
        assert result_a is True
        result_b = await VerifyCodeStore.verify_and_delete("reset", email_b, code_reset)
        assert result_b is True


class TestVerifyCodeStoreRateLimit:
    """限流测试"""

    @pytest.mark.asyncio
    async def test_rate_limit_per_minute(self):
        """1 分钟内重复发送被限流"""
        from utils.http.http_exceptions import AppError

        email = "rate@example.com"
        await VerifyCodeStore.generate_and_store("register", email)

        with pytest.raises(AppError) as exc_info:
            await VerifyCodeStore.generate_and_store("register", email)
        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_different_emails_no_conflict(self):
        """不同邮箱之间不互相限流"""
        await VerifyCodeStore.generate_and_store("register", "a@example.com")
        code = await VerifyCodeStore.generate_and_store("register", "b@example.com")
        assert len(code) == 6


class TestVerifyCodeStoreVerify:
    """验证码校验测试"""

    @pytest.mark.asyncio
    async def test_verify_correct_code(self):
        """正确验证码校验通过"""
        email = "verify@example.com"
        code = await VerifyCodeStore.generate_and_store("register", email)

        result = await VerifyCodeStore.verify_and_delete("register", email, code)
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_wrong_code(self):
        """错误验证码校验失败"""
        email = "wrong@example.com"
        await VerifyCodeStore.generate_and_store("register", email)

        result = await VerifyCodeStore.verify_and_delete("register", email, "000000")
        assert result is False

    @pytest.mark.asyncio
    async def test_verify_expired_code(self):
        """过期验证码校验失败"""
        email = "expired@example.com"
        # 不生成验证码，直接尝试校验
        result = await VerifyCodeStore.verify_and_delete("register", email, "123456")
        assert result is False

    @pytest.mark.asyncio
    async def test_verify_deletes_code(self):
        """校验通过后验证码被删除，不可重复使用"""
        email = "oneuse@example.com"
        code = await VerifyCodeStore.generate_and_store("register", email)

        result1 = await VerifyCodeStore.verify_and_delete("register", email, code)
        assert result1 is True

        result2 = await VerifyCodeStore.verify_and_delete("register", email, code)
        assert result2 is False

    @pytest.mark.asyncio
    async def test_verify_wrong_reason(self):
        """用错误的 reason 校验失败"""
        email = "reason@example.com"
        code = await VerifyCodeStore.generate_and_store("register", email)

        result = await VerifyCodeStore.verify_and_delete("reset", email, code)
        assert result is False
