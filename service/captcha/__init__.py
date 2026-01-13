import abc
import aiohttp

from pydantic import BaseModel

from .gcaptcha import GCaptcha
from .turnstile import TurnstileCaptcha


class CaptchaRequestBase(BaseModel):
    """验证码验证请求"""
    token: str
    """验证 token"""
    secret: str
    """验证密钥"""


class CaptchaBase(abc.ABC):
    """验证码验证器抽象基类"""

    verify_url: str
    """验证 API 地址（子类必须定义）"""

    async def verify_captcha(self, request: CaptchaRequestBase) -> bool:
        """
        验证 token 是否有效。

        :return: 如果验证成功返回 True，否则返回 False
        :rtype: bool
        """
        payload = request.model_dump()

        async with aiohttp.ClientSession() as session:
            async with session.post(self.verify_url, data=payload) as response:
                if response.status != 200:
                    return False

                result = await response.json()
                return result.get('success', False)