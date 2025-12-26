import aiohttp

from . import CaptchaRequestBase

async def verify_captcha(request: CaptchaRequestBase) -> bool:
    """
    验证 Google reCAPTCHA v2/v3 的 token 是否有效。
    
    :return: 如果验证成功返回 True，否则返回 False
    :rtype: bool
    """
    verify_url = "https://www.google.com/recaptcha/api/siteverify"
    payload = request.model_dump()
    
    async with aiohttp.ClientSession() as session:
        async with session.post(verify_url, data=payload) as response:
            if response.status != 200:
                return False
            
            result = await response.json()
            return result.get('success', False)