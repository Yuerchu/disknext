"""
SMS 提供商基类单元测试

测试 SmsProvider 的验证码生成、Redis 限流、Lua 原子验证、暴力破解防护等逻辑。
基于真实 Redis 实例。
"""
import pytest

from utils.redis import RedisManager
from sqlmodels.sms.base import (
    SmsProvider,
    SmsCodeReasonEnum,
    SmsRateLimitException,
    SmsCodeInvalidException,
)


class TestSmsProviderVerifyCode:
    """SmsProvider.verify_code 原子校验测试"""

    @pytest.mark.asyncio
    async def test_verify_correct_code(self):
        """正确验证码校验通过"""
        phone = "+8613800000001"
        reason = SmsCodeReasonEnum.login
        code = "123456"

        client = RedisManager.get_client()
        await client.set(f"sms_code:{reason}:code:{phone}", code, ex=300)

        is_valid, msg = await SmsProvider.verify_code(phone, code, reason, 300)
        assert is_valid is True
        assert msg == ""

    @pytest.mark.asyncio
    async def test_verify_wrong_code(self):
        """错误验证码校验失败"""
        phone = "+8613800000002"
        reason = SmsCodeReasonEnum.login
        code = "123456"

        client = RedisManager.get_client()
        await client.set(f"sms_code:{reason}:code:{phone}", code, ex=300)

        is_valid, msg = await SmsProvider.verify_code(phone, "999999", reason, 300)
        assert is_valid is False
        assert msg == "验证码无效"

    @pytest.mark.asyncio
    async def test_verify_expired_code(self):
        """未存储的验证码返回失败"""
        phone = "+8613800000003"
        reason = SmsCodeReasonEnum.login

        is_valid, msg = await SmsProvider.verify_code(phone, "123456", reason, 300)
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_verify_deletes_code_on_success(self):
        """验证成功后验证码被删除"""
        phone = "+8613800000004"
        reason = SmsCodeReasonEnum.login
        code = "654321"

        client = RedisManager.get_client()
        await client.set(f"sms_code:{reason}:code:{phone}", code, ex=300)

        is_valid, _ = await SmsProvider.verify_code(phone, code, reason, 300)
        assert is_valid is True

        # 第二次校验应该失败
        is_valid2, _ = await SmsProvider.verify_code(phone, code, reason, 300)
        assert is_valid2 is False

    @pytest.mark.asyncio
    async def test_verify_lockout_after_max_attempts(self):
        """超过最大尝试次数后验证码被锁定"""
        phone = "+8613800000005"
        reason = SmsCodeReasonEnum.login
        code = "111111"

        client = RedisManager.get_client()
        await client.set(f"sms_code:{reason}:code:{phone}", code, ex=300)

        # 连续 5 次错误尝试（应触发锁定，验证码被删除）
        # 注意：debug 模式下 "000000" 是万能验证码，需要用其他值
        for _ in range(5):
            await SmsProvider.verify_code(phone, "999998", reason, 300)

        # 第 6 次即使正确也应该失败（验证码已被删除）
        is_valid, _ = await SmsProvider.verify_code(phone, code, reason, 300)
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_different_reasons_isolated(self):
        """不同 reason 的验证码互相隔离"""
        phone = "+8613800000006"
        login_code = "111111"
        register_code = "222222"

        client = RedisManager.get_client()
        await client.set(f"sms_code:login:code:{phone}", login_code, ex=300)
        await client.set(f"sms_code:register:code:{phone}", register_code, ex=300)

        # login reason 用 register 的 code 校验失败
        is_valid, _ = await SmsProvider.verify_code(phone, register_code, SmsCodeReasonEnum.login, 300)
        assert is_valid is False

        # register reason 用 register 的 code 校验成功
        is_valid, _ = await SmsProvider.verify_code(phone, register_code, SmsCodeReasonEnum.register, 300)
        assert is_valid is True


class TestSmsProviderLockout:
    """SmsProvider 账户锁定机制测试"""

    @pytest.mark.asyncio
    async def test_check_lockout_not_locked(self):
        """未锁定的手机号不抛异常"""
        phone = "+8613800000010"
        await SmsProvider.check_lockout(phone)  # 不应抛异常

    @pytest.mark.asyncio
    async def test_check_lockout_locked(self):
        """已锁定的手机号抛出 SmsRateLimitException"""
        phone = "+8613800000011"
        client = RedisManager.get_client()
        await client.set(f"sms_code:lockout:{phone}", "1", ex=900)

        with pytest.raises(SmsRateLimitException):
            await SmsProvider.check_lockout(phone)

    @pytest.mark.asyncio
    async def test_record_failure_locks_after_5(self):
        """连续 5 次失败后触发锁定"""
        phone = "+8613800000012"

        for _ in range(5):
            await SmsProvider.record_failure(phone, lockout_ttl=900)

        client = RedisManager.get_client()
        assert await client.exists(f"sms_code:lockout:{phone}")

    @pytest.mark.asyncio
    async def test_clear_attempts(self):
        """清除失败记录"""
        phone = "+8613800000013"
        await SmsProvider.record_failure(phone, lockout_ttl=900)

        client = RedisManager.get_client()
        assert await client.exists(f"sms_code:lockout_attempts:{phone}")

        await SmsProvider.clear_attempts(phone)
        assert not await client.exists(f"sms_code:lockout_attempts:{phone}")

    @pytest.mark.asyncio
    async def test_verify_and_enforce_success(self):
        """verify_and_enforce 成功流程"""
        phone = "+8613800000014"
        reason = SmsCodeReasonEnum.login
        code = "999999"

        client = RedisManager.get_client()
        await client.set(f"sms_code:{reason}:code:{phone}", code, ex=300)

        # 不应抛异常
        await SmsProvider.verify_and_enforce(phone, code, reason, 300)

    @pytest.mark.asyncio
    async def test_verify_and_enforce_invalid_raises(self):
        """verify_and_enforce 验证码错误抛出 SmsCodeInvalidException"""
        phone = "+8613800000015"
        reason = SmsCodeReasonEnum.login

        client = RedisManager.get_client()
        await client.set(f"sms_code:{reason}:code:{phone}", "111111", ex=300)

        with pytest.raises(SmsCodeInvalidException):
            await SmsProvider.verify_and_enforce(phone, "999997", reason, 300)

    @pytest.mark.asyncio
    async def test_verify_and_enforce_lockout_raises(self):
        """verify_and_enforce 锁定状态抛出 SmsRateLimitException"""
        phone = "+8613800000016"
        reason = SmsCodeReasonEnum.login

        client = RedisManager.get_client()
        await client.set(f"sms_code:lockout:{phone}", "1", ex=900)

        with pytest.raises(SmsRateLimitException):
            await SmsProvider.verify_and_enforce(phone, "123456", reason, 300)


class TestSmsProviderGenerateCode:
    """SmsProvider._generate_code 测试"""

    def test_generate_code_format(self):
        """生成 6 位零填充数字字符串"""
        for _ in range(100):
            code = SmsProvider._generate_code()
            assert len(code) == 6
            assert code.isdigit()
