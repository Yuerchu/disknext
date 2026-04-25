import abc
from enum import StrEnum

import aiohttp
from loguru import logger as l
from pydantic import BaseModel

from sqlmodels import ServerConfig, CaptchaType
from utils import http_exceptions
from utils.http.error_codes import ErrorCode as E

class CaptchaRequestBase(BaseModel):
    """验证码验证请求"""

    response: str
    """用户的验证码 response token"""

    secret: str
    """服务端密钥"""


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

        async with aiohttp.ClientSession() as client_session:
            async with client_session.post(self.verify_url, data=payload) as resp:
                if resp.status != 200:
                    return False

                result = await resp.json()
                return result.get('success', False)


# 子类导入必须在 CaptchaBase 定义之后（gcaptcha.py / turnstile.py 依赖 CaptchaBase）
from .gcaptcha import GCaptcha  # noqa: E402
from .turnstile import TurnstileCaptcha  # noqa: E402


class CaptchaScene(StrEnum):
    """验证码使用场景"""

    LOGIN = "login_captcha"
    REGISTER = "reg_captcha"
    FORGET = "forget_captcha"


async def verify_captcha_if_needed(
        config: ServerConfig,
        scene: CaptchaScene,
        captcha_code: str | None,
) -> None:
    """
    通用验证码校验：根据 ServerConfig 判断是否需要，需要则校验。

    :param config: 服务器配置
    :param scene: 验证码使用场景
    :param captcha_code: 用户提交的验证码 response token
    :raises HTTPException 400: 需要验证码但未提供
    :raises HTTPException 403: 验证码验证失败
    :raises HTTPException 500: 验证码密钥未配置
    """

    # 1. 检查场景是否需要验证码
    is_scene_enabled: bool = {
        CaptchaScene.LOGIN: config.is_login_captcha,
        CaptchaScene.REGISTER: config.is_reg_captcha,
        CaptchaScene.FORGET: config.is_forget_captcha,
    }.get(scene, False)

    if not is_scene_enabled:
        return
    
    if not captcha_code:
        http_exceptions.raise_bad_request(E.CAPTCHA_REQUIRED, "需要验证码但未提供")

    # 2. DEFAULT 图片验证码尚未实现，跳过
    if config.captcha_type == CaptchaType.DEFAULT:
        l.warning("DEFAULT 图片验证码尚未实现，跳过验证")
        return

    # 3. 选择验证器和密钥
    if config.captcha_type == CaptchaType.GCAPTCHA:
        secret = config.captcha_recaptcha_secret
        verifier: CaptchaBase = GCaptcha()
    elif config.captcha_type == CaptchaType.CLOUD_FLARE_TURNSTILE:
        secret = config.captcha_cloudflare_secret
        verifier = TurnstileCaptcha()
    else:
        l.error(f"未知的验证码类型: {config.captcha_type}")
        http_exceptions.raise_internal_error()

    if not secret:
        l.error(f"验证码密钥未配置: captcha_type={config.captcha_type}")
        http_exceptions.raise_internal_error()

    # 4. 调用第三方 API 校验
    is_valid = await verifier.verify_captcha(
        CaptchaRequestBase(response=captcha_code, secret=secret)
    )
    if not is_valid:
        http_exceptions.raise_forbidden(E.CAPTCHA_INVALID, "验证码验证失败")
