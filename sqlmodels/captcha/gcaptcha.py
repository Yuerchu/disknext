from . import CaptchaBase


class GCaptcha(CaptchaBase):
    """Google reCAPTCHA v2/v3 验证器"""

    verify_url = "https://www.google.com/recaptcha/api/siteverify"