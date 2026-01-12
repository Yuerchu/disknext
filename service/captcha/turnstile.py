from . import CaptchaBase


class TurnstileCaptcha(CaptchaBase):
    """Cloudflare Turnstile 验证器"""

    verify_url = "https://challenges.cloudflare.com/turnstile/v0/siteverify"