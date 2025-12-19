import pyotp


def verify_totp(secret: str, code: str) -> bool:
    """
    验证 TOTP 验证码。

    :param secret: TOTP 密钥（Base32 编码）
    :param code: 用户输入的 6 位验证码
    :return: 验证是否成功
    """
    totp = pyotp.TOTP(secret)
    return totp.verify(code)
