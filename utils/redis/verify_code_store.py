"""
邮箱验证码 Redis 存储

提供 6 位数字验证码的生成、存储、限流和原子校验。
"""
import secrets

from loguru import logger as l

from utils import http_exceptions
from utils.http.error_codes import ErrorCode as E
from utils.redis import RedisManager


_RATE_LIMIT_PER_MINUTE = 1
"""每分钟最多发送次数"""

_RATE_LIMIT_PER_HOUR = 5
"""每小时最多发送次数"""

_VERIFY_AND_DELETE_LUA = """
local stored = redis.call('GET', KEYS[1])
if stored == false then
    return 0
end
if stored == ARGV[1] then
    redis.call('DEL', KEYS[1])
    return 1
end
return 0
"""
"""原子校验+删除 Lua 脚本"""


class VerifyCodeStore:
    """
    邮箱验证码 Redis 存储

    Key 约定：
    - 验证码: ``verify_code:{reason}:{email}``
    - 分钟限流: ``verify_rate_min:{email}``
    - 小时限流: ``verify_rate_hour:{email}``
    """

    def __new__(cls, *args: object, **kwargs: object) -> 'VerifyCodeStore':
        raise RuntimeError(f"{cls.__name__} 是纯 classmethod 单例，禁止实例化")

    @classmethod
    async def generate_and_store(cls, reason: str, email: str, ttl_minutes: int = 10) -> str:
        """
        生成 6 位验证码并存储到 Redis。

        :param reason: 用途标识（register / reset）
        :param email: 邮箱地址
        :param ttl_minutes: 验证码有效期（分钟）
        :return: 6 位数字验证码
        :raises AppError: 发送过于频繁时抛出 429
        """
        client = RedisManager.get_client()

        # 限流检查：1 分钟内只能发 1 次
        rate_min_key = f"verify_rate_min:{email}"
        min_count = await client.get(rate_min_key)
        if min_count is not None:
            http_exceptions.raise_too_many_requests(E.MAIL_RATE_LIMITED, "发送过于频繁，请稍后再试")

        # 限流检查：1 小时内最多 5 次
        rate_hour_key = f"verify_rate_hour:{email}"
        hour_count_raw = await client.get(rate_hour_key)
        if hour_count_raw is not None and int(hour_count_raw) >= _RATE_LIMIT_PER_HOUR:
            http_exceptions.raise_too_many_requests(E.MAIL_RATE_LIMITED, "发送次数已达上限，请一小时后再试")

        # 生成 6 位数字验证码
        code = f"{secrets.randbelow(1000000):06d}"

        # 存储验证码
        code_key = f"verify_code:{reason}:{email}"
        await client.set(code_key, code.encode(), ex=ttl_minutes * 60)

        # 更新限流计数
        await client.set(rate_min_key, b"1", ex=60)

        if hour_count_raw is None:
            await client.set(rate_hour_key, b"1", ex=3600)
        else:
            await client.incr(rate_hour_key)

        l.info(f"验证码已生成: reason={reason}, email={email}")
        return code

    @classmethod
    async def verify_and_delete(cls, reason: str, email: str, code: str) -> bool:
        """
        原子校验并删除验证码（Lua 脚本防竞态）。

        :param reason: 用途标识
        :param email: 邮箱地址
        :param code: 用户输入的验证码
        :return: True 验证通过，False 验证码错误或已过期
        """
        client = RedisManager.get_client()
        code_key = f"verify_code:{reason}:{email}"

        result = await client.eval(
            _VERIFY_AND_DELETE_LUA,
            1,
            code_key,
            code.encode(),
        )

        if result == 1:
            l.info(f"验证码校验通过: reason={reason}, email={email}")
            return True

        l.debug(f"验证码校验失败: reason={reason}, email={email}")
        return False
