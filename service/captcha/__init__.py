import abc
from enum import StrEnum

import aiohttp
from loguru import logger as l
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession


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
    """验证码使用场景，value 对应 Setting 表中的 name"""

    LOGIN = "login_captcha"
    REGISTER = "reg_captcha"
    FORGET = "forget_captcha"


async def verify_captcha_if_needed(
        session: AsyncSession,
        scene: CaptchaScene,
        captcha_code: str | None,
) -> None:
    """
    通用验证码校验：查询设置判断是否需要，需要则校验。

    :param session: 数据库异步会话
    :param scene: 验证码使用场景
    :param captcha_code: 用户提交的验证码 response token
    :raises HTTPException 400: 需要验证码但未提供
    :raises HTTPException 403: 验证码验证失败
    :raises HTTPException 500: 验证码密钥未配置
    """
    from sqlmodels import Setting, SettingsType
    from sqlmodels.setting import CaptchaType
    from utils import http_exceptions

    # 1. 查询该场景是否需要验证码
    scene_setting = await Setting.get(
        session,
        (Setting.type == SettingsType.LOGIN) & (Setting.name == scene.value),
    )
    if not scene_setting or scene_setting.value != "1":
        return

    # 2. 需要但未提供
    if not captcha_code:
        http_exceptions.raise_bad_request(detail="请完成验证码验证")

    # 3. 查询验证码类型和密钥
    captcha_settings: list[Setting] = await Setting.get(
        session, Setting.type == SettingsType.CAPTCHA, fetch_mode="all",
    )
    s: dict[str, str | None] = {item.name: item.value for item in captcha_settings}
    captcha_type = CaptchaType(s.get("captcha_type") or "default")

    # 4. DEFAULT 图片验证码尚未实现，跳过
    if captcha_type == CaptchaType.DEFAULT:
        l.warning("DEFAULT 图片验证码尚未实现，跳过验证")
        return

    # 5. 选择验证器和密钥
    if captcha_type == CaptchaType.GCAPTCHA:
        secret = s.get("captcha_ReCaptchaSecret")
        verifier: CaptchaBase = GCaptcha()
    elif captcha_type == CaptchaType.CLOUD_FLARE_TURNSTILE:
        secret = s.get("captcha_CloudflareSecret")
        verifier = TurnstileCaptcha()
    else:
        l.error(f"未知的验证码类型: {captcha_type}")
        http_exceptions.raise_internal_error()

    if not secret:
        l.error(f"验证码密钥未配置: captcha_type={captcha_type}")
        http_exceptions.raise_internal_error()

    # 6. 调用第三方 API 校验
    is_valid = await verifier.verify_captcha(
        CaptchaRequestBase(response=captcha_code, secret=secret)
    )
    if not is_valid:
        http_exceptions.raise_forbidden(detail="验证码验证失败")
