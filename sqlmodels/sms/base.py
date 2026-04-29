"""
短信验证码提供商配置和运行时类

使用联表继承实现多态短信提供商配置。
Redis 缓存实现：Lua 脚本原子验证 + 暴力破解防护（5 次尝试限制）
"""
import asyncio
import random
import secrets
from abc import ABC, abstractmethod
from collections.abc import Awaitable
from enum import StrEnum
from typing import ClassVar, cast

from loguru import logger as l
from pydantic_extra_types.phone_numbers import PhoneNumber
from redis.asyncio import Redis

from sqlmodel_ext import SQLModelBase, UUIDTableBaseMixin, PolymorphicBaseMixin, Str64

from utils.aiohttp_session import AioHttpClientSessionClassVarMixin
from utils.redis import RedisManager


# Lua 脚本：原子验证验证码
# KEYS[1] = sms_code:{reason}:code:{phone}
# KEYS[2] = sms_code:{reason}:attempts:{phone}
# ARGV[1] = user_input_code
# ARGV[2] = max_attempts (5)
# ARGV[3] = ttl (300)
# 返回: 1=成功, 0=验证码错误, -1=已锁定, -2=验证码不存在
_VERIFY_CODE_SCRIPT: str = '''
local stored_code = redis.call('GET', KEYS[1])
if not stored_code then
    return -2
end

local attempts = redis.call('INCR', KEYS[2])
redis.call('EXPIRE', KEYS[2], ARGV[3])

if attempts > tonumber(ARGV[2]) then
    redis.call('DEL', KEYS[1])
    redis.call('DEL', KEYS[2])
    return -1
end

if stored_code == ARGV[1] then
    redis.call('DEL', KEYS[1])
    redis.call('DEL', KEYS[2])
    return 1
end

return 0
'''


# ==================== 异常层次 ====================

class SmsException(Exception):
    """短信验证码异常基类"""


class SmsProviderException(SmsException):
    """短信提供商上游错误（API 返回的错误）"""


class SmsRateLimitException(SmsException):
    """短信发送频率限制错误"""


class SmsInternalException(SmsException):
    """短信模块内部非预期错误（网络错误、配置错误等）"""


class SmsCodeInvalidException(SmsException):
    """验证码无效（错误、过期、尝试次数过多）"""


# ==================== 枚举 ====================

class SmsCodeTypeEnum(StrEnum):
    """验证码类型枚举"""
    sms = 'sms'
    """短信验证码"""

    voice = 'voice'
    """语音验证码"""


class SmsCodeReasonEnum(StrEnum):
    """验证码用途枚举，用于 Redis 键隔离"""
    login = 'login'
    """登录"""

    register = 'register'
    """注册"""

    reset_password = 'reset_password'
    """重置密码"""

    change_phone = 'change_phone'
    """修改手机号"""


# ==================== DTO ====================

class SendSmsCodeRequest(SQLModelBase):
    """发送短信验证码请求"""
    phone_number: PhoneNumber
    """手机号（E.164 格式，如 +8613800138000）"""

    reason: SmsCodeReasonEnum
    """验证码用途"""

    code_type: SmsCodeTypeEnum = SmsCodeTypeEnum.sms
    """验证码类型"""


class SmsProviderBase(SQLModelBase):
    """短信提供商配置基类"""

    name: Str64
    """配置名称，如'短信宝'、'腾讯云短信'"""

    enabled: bool = True
    """是否启用此提供商"""


# ==================== 抽象基类 ====================

class SmsProvider(
    SmsProviderBase,
    UUIDTableBaseMixin,
    PolymorphicBaseMixin,
    AioHttpClientSessionClassVarMixin,
    ABC,
    polymorphic_abstract=True,
):
    """
    短信提供商抽象基类

    使用联表继承实现多态短信提供商配置。

    提供运行时方法：
    - send_verification_code(): 发送短信验证码（自动生成 code 并缓存）
    - send_voice_code(): 发送语音验证码
    - verify_code(): 验证验证码
    - verify_and_enforce(): 完整验证流程（锁定检查 + 校验 + 失败记录）

    验证码设计：
    - 全局共享验证码缓存：所有提供商实例共享同一个 Redis 验证码缓存
    - Redis TTL 自动过期
    - 冗余机制：端点会依次尝试多个提供商
    - 异常分层：区分上游 API 错误、频率限制、内部错误
    """
    _MAX_ATTEMPTS: ClassVar[int] = 5
    """最大尝试次数"""

    _MAX_LOCKOUT_ATTEMPTS: ClassVar[int] = 5
    """验证失败触发锁定的最大次数（全局，不区分 reason）"""

    _verify_script_sha: ClassVar[str | None] = None
    """Lua 脚本 SHA 缓存"""

    @staticmethod
    def _generate_code() -> str:
        """生成 6 位随机数字验证码"""
        return str(secrets.randbelow(1_000_000)).zfill(6)

    async def _check_rate_limit(self, phone_number: str) -> None:
        """
        检查发送频率限制

        :raises SmsRateLimitException: 发送过于频繁时抛出
        """
        client = RedisManager.get_client()
        if await client.exists(f"sms_code:rate:{phone_number}"):
            raise SmsRateLimitException("发送过于频繁，请稍后再试")

    async def _cache_code(
        self,
        phone_number: str,
        code: str,
        reason: SmsCodeReasonEnum,
        code_ttl: int,
        rate_limit_ttl: int,
    ) -> None:
        """
        缓存验证码并设置频率限制

        :param phone_number: 手机号
        :param code: 验证码
        :param reason: 验证码用途
        :param code_ttl: 验证码有效期（秒）
        :param rate_limit_ttl: 频率限制时间（秒）
        """
        client = RedisManager.get_client()
        pipe = client.pipeline(transaction=True)
        pipe.setex(f"sms_code:{reason}:code:{phone_number}", code_ttl, code)
        pipe.setex(f"sms_code:rate:{phone_number}", rate_limit_ttl, "1")
        # 重置尝试次数（重新发送验证码时）
        pipe.delete(f"sms_code:{reason}:attempts:{phone_number}")
        await pipe.execute()
        l.debug(f"短信验证码已缓存: {phone_number} (reason={reason})")

    @classmethod
    async def verify_code(
        cls,
        phone_number: str,
        code: str,
        reason: SmsCodeReasonEnum,
        code_ttl: int,
    ) -> tuple[bool, str]:
        """
        验证验证码（原子操作，带暴力破解防护）

        使用 Lua 脚本实现原子验证，防止 TOCTOU 竞态条件。
        5 次尝试失败后自动锁定验证码。

        :param phone_number: 手机号
        :param code: 用户输入的验证码
        :param reason: 验证码用途
        :param code_ttl: 验证码有效期（秒）
        :return: (是否成功, 错误消息)
        """
        from utils.conf import appmeta

        # 调试模式万能验证码旁路
        if appmeta.debug and code == "000000":
            l.warning(f"DEBUG 万能验证码旁路: {phone_number}")
            return (True, "")

        client = RedisManager.get_client()

        # 确保 Lua 脚本已加载
        if cls._verify_script_sha is None:
            cls._verify_script_sha = await client.script_load(_VERIFY_CODE_SCRIPT)

        result = await cast(Awaitable[int], client.evalsha(
            cast(str, cls._verify_script_sha),
            2,
            f"sms_code:{reason}:code:{phone_number}",
            f"sms_code:{reason}:attempts:{phone_number}",
            code,
            str(cls._MAX_ATTEMPTS),
            str(code_ttl),
        ))

        match result:
            case 1:
                l.info(f"短信验证码验证成功: {phone_number} (reason={reason})")
                return (True, "")
            case 0 | -1 | -2 | _:
                # 防止时序攻击：添加随机延迟（50-150ms）
                await asyncio.sleep(0.05 + random.random() * 0.1)
                if result == 0:
                    l.warning(f"短信验证码错误: {phone_number} (reason={reason})")
                elif result == -1:
                    l.warning(f"短信验证码尝试次数过多: {phone_number} (reason={reason})")
                elif result == -2:
                    l.warning(f"短信验证码不存在或已过期: {phone_number} (reason={reason})")
                return (False, "验证码无效")

    @classmethod
    async def check_lockout(cls, phone_number: str) -> None:
        """
        检查账户是否被锁定

        :raises SmsRateLimitException: 账户被锁定时抛出
        """
        client = RedisManager.get_client()
        lockout_key = f"sms_code:lockout:{phone_number}"
        if await client.exists(lockout_key):
            ttl = await client.ttl(lockout_key)
            minutes = ttl // 60
            raise SmsRateLimitException(
                f"验证失败次数过多，账户已锁定{minutes}分钟，请稍后再试"
            )

    @classmethod
    async def record_failure(cls, phone_number: str, lockout_ttl: int) -> None:
        """
        记录验证失败，连续失败 5 次后锁定账户

        :param phone_number: 手机号
        :param lockout_ttl: 锁定时间（秒）
        """
        client = RedisManager.get_client()
        attempts_key = f"sms_code:lockout_attempts:{phone_number}"
        lockout_key = f"sms_code:lockout:{phone_number}"

        attempts = await client.incr(attempts_key)
        if attempts == 1:
            await client.expire(attempts_key, 900)

        if attempts >= cls._MAX_LOCKOUT_ATTEMPTS:
            pipe = client.pipeline(transaction=True)
            pipe.setex(lockout_key, lockout_ttl, "1")
            pipe.delete(attempts_key)
            await pipe.execute()
            l.warning(f"验证失败次数过多，账户已锁定: {phone_number}")

    @classmethod
    async def clear_attempts(cls, phone_number: str) -> None:
        """清除验证失败记录（验证成功时调用）"""
        client = RedisManager.get_client()
        await client.delete(f"sms_code:lockout_attempts:{phone_number}")

    @classmethod
    async def verify_and_enforce(
        cls,
        phone: str,
        code: str,
        reason: SmsCodeReasonEnum,
        code_ttl: int,
        lockout_ttl: int = 900,
    ) -> None:
        """
        完整验证流程：锁定检查 → 验证码验证 → 失败记录/成功清理

        :param phone: 手机号
        :param code: 用户输入的验证码
        :param reason: 验证码用途
        :param code_ttl: 验证码有效期（秒）
        :param lockout_ttl: 锁定时间（秒）
        :raises SmsRateLimitException: 账户被锁定
        :raises SmsCodeInvalidException: 验证码无效
        """
        await cls.check_lockout(phone)

        is_valid, error_msg = await cls.verify_code(phone, code, reason, code_ttl)
        if not is_valid:
            await cls.record_failure(phone, lockout_ttl)
            raise SmsCodeInvalidException(error_msg)

        await cls.clear_attempts(phone)

    @abstractmethod
    async def _send_sms(self, phone_number: str, code: str, code_ttl: int) -> bool:
        """
        发送短信验证码的底层实现

        :param phone_number: 接收验证码的手机号（E.164 格式）
        :param code: 验证码内容
        :param code_ttl: 验证码有效期（秒）
        :return: 是否发送成功
        :raises SmsProviderException: 上游 API 错误
        :raises SmsInternalException: 内部非预期错误
        """
        raise NotImplementedError

    async def send_verification_code(
        self,
        phone_number: str,
        reason: SmsCodeReasonEnum,
        code_ttl: int,
        rate_limit_ttl: int,
    ) -> str:
        """
        发送短信验证码（高层接口）

        自动生成验证码、检查频率限制、发送短信、缓存验证码。

        :param phone_number: 接收验证码的手机号
        :param reason: 验证码用途
        :param code_ttl: 验证码有效期（秒）
        :param rate_limit_ttl: 频率限制时间（秒）
        :return: 生成的验证码
        :raises SmsRateLimitException: 发送频率超限
        :raises SmsProviderException: 上游 API 错误
        :raises SmsInternalException: 内部非预期错误
        """
        if not self.enabled:
            raise SmsInternalException("短信提供商未启用")

        await self._check_rate_limit(phone_number)

        # 删除旧验证码（防止多窗口重放攻击）
        client = RedisManager.get_client()
        await client.delete(f"sms_code:{reason}:code:{phone_number}")

        code = self._generate_code()
        success = await self._send_sms(phone_number, code, code_ttl)

        if success:
            await self._cache_code(phone_number, code, reason, code_ttl, rate_limit_ttl)

        return code

    @abstractmethod
    async def _send_voice_code(self, phone_number: str, code: str) -> bool:
        """
        发送语音验证码的底层实现

        :param phone_number: 接收验证码的手机号
        :param code: 验证码内容
        :return: 是否发送成功
        :raises SmsProviderException: 上游 API 错误
        :raises SmsInternalException: 内部非预期错误
        """
        raise NotImplementedError

    async def send_voice_code(
        self,
        phone_number: str,
        reason: SmsCodeReasonEnum,
        code_ttl: int,
        rate_limit_ttl: int,
    ) -> str:
        """
        发送语音验证码

        :param phone_number: 接收验证码的手机号
        :param reason: 验证码用途
        :param code_ttl: 验证码有效期（秒）
        :param rate_limit_ttl: 频率限制时间（秒）
        :return: 验证码内容
        """
        if not self.enabled:
            raise SmsInternalException("短信提供商未启用")

        await self._check_rate_limit(phone_number)

        client = RedisManager.get_client()
        await client.delete(f"sms_code:{reason}:code:{phone_number}")

        code = self._generate_code()
        success = await self._send_voice_code(phone_number, code)

        if success:
            await self._cache_code(phone_number, code, reason, code_ttl, rate_limit_ttl)

        return code
