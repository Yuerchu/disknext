import secrets

from loguru import logger
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from enum import StrEnum
import pyotp
from itsdangerous import URLSafeTimedSerializer
from pydantic import BaseModel, Field

from utils.JWT import SECRET_KEY
from utils.conf import appmeta

_ph = PasswordHasher()

class PasswordStatus(StrEnum):
    """密码校验状态枚举"""

    VALID = "valid"
    """密码校验通过"""

    INVALID = "invalid"
    """密码校验失败"""

    EXPIRED = "expired"
    """密码哈希已过时，建议重新哈希"""

class TwoFactorBase(BaseModel):
    """两步验证请求 DTO"""

    setup_token: str
    """用于验证的令牌"""

class TwoFactorResponse(TwoFactorBase):
    """两步验证-请求启用时的响应 DTO"""

    uri: str
    """用于生成二维码的 URI"""

class TwoFactorVerifyRequest(TwoFactorBase):
    """两步验证-验证请求 DTO"""

    code: int = Field(..., ge=100000, le=999999)
    """6 位验证码"""

class Password:
    """密码处理工具类，包含密码生成、哈希和验证功能"""

    @staticmethod
    def generate(
            length: int = 8
    ) -> str:
        """
        生成指定长度的随机密码。

        :param length: 密码长度
        :type length: int
        :return: 随机密码
        :rtype: str
        """
        return secrets.token_hex(length)

    @staticmethod
    def hash(
            password: str
    ) -> str:
        """
        使用 Argon2 生成密码的哈希值。

        返回的哈希字符串已经包含了所有需要验证的信息（盐、算法参数等）。

        :param password: 需要哈希的原始密码
        :return: Argon2 哈希字符串
        """
        return _ph.hash(password)

    @staticmethod
    def verify(
            hash: str,
            password: str
    ) -> PasswordStatus:
        """
        验证存储的 Argon2 哈希值与用户提供的密码是否匹配。

        :param hash: 数据库中存储的 Argon2 哈希字符串
        :param password: 用户本次提供的密码
        :return: 如果密码匹配返回 True, 否则返回 False
        """
        try:
            # verify 函数会自动解析 stored_password 中的盐和参数
            _ph.verify(hash, password)

            # 检查哈希参数是否已过时。如果返回True，
            # 意味着你应该使用新的参数重新哈希密码并更新存储。
            # 这是一个很好的实践，可以随着时间推移增强安全性。
            if _ph.check_needs_rehash(hash):
                logger.warning("密码哈希参数已过时，建议重新哈希并更新。")
                return PasswordStatus.EXPIRED

            return PasswordStatus.VALID
        except VerifyMismatchError:
            # 这是预期的异常，当密码不匹配时触发。
            return PasswordStatus.INVALID
        # 其他异常（如哈希格式错误）应该传播，让调用方感知系统问题
    
    @staticmethod
    async def generate_totp(
        *args, **kwargs
    ) -> TwoFactorResponse:
        """
        生成 TOTP 密钥和对应的 URI，用于两步验证。
        所有的参数将会给到 `pyotp.totp.TOTP`

        :return: 包含 TOTP 密钥和 URI 的元组
        """

        serializer = URLSafeTimedSerializer(SECRET_KEY)

        secret = pyotp.random_base32()

        setup_token = serializer.dumps(
            secret,
            salt="2fa-setup-salt"
        )

        otp_uri = pyotp.totp.TOTP(secret, *args, **kwargs).provisioning_uri(
            issuer_name=appmeta.APP_NAME
        )

        return TwoFactorResponse(
            uri=otp_uri,
            setup_token=setup_token
        )
    
    @staticmethod
    def verify_totp(
            secret: str,
            code: int,
            *args, **kwargs
    ) -> PasswordStatus:
        """
        验证 TOTP 验证码。

        :param secret: TOTP 密钥（Base32 编码）
        :param code: 用户输入的 6 位验证码
        :param args: 传入 `totp.verify` 的参数
        :param kwargs: 传入 `totp.verify` 的参数
        
        :return: 验证是否成功
        """
        totp = pyotp.TOTP(secret)
        if totp.verify(otp=str(code), *args, **kwargs):
            return PasswordStatus.VALID
        else:
            return PasswordStatus.INVALID