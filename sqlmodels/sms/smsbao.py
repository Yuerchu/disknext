"""
短信宝验证码提供商

文档：https://www.smsbao.com/api.shtml
"""
import phonenumbers
from loguru import logger as l
from sqlmodel_ext import AutoPolymorphicIdentityMixin, SQLModelBase, Str64, Str256

from .base import (
    SmsProvider,
    SmsProviderBase,
    SmsProviderException,
    SmsInternalException,
)


class SMSBaoProvider(
    SmsProvider,
    AutoPolymorphicIdentityMixin,
    table=True,
):
    """
    短信宝验证码提供商

    文档：https://www.smsbao.com/api.shtml
    """

    username: str
    """短信宝账号"""

    password: str
    """短信宝密码 MD5"""

    template: str
    """短信模板，使用 {code} 作为验证码占位符，{time} 作为有效期（分钟）占位符"""

    @staticmethod
    def _handle_result(response_text: str) -> bool:
        """
        处理短信宝 API 响应

        :param response_text: API 返回的状态码
        :return: 是否成功
        :raises SmsProviderException: 上游 API 错误
        """
        match response_text:
            case '0':
                return True
            case '30':
                raise SmsProviderException("密码错误")
            case '40':
                raise SmsProviderException("账号不存在")
            case '41':
                raise SmsProviderException("余额不足")
            case '42':
                raise SmsProviderException("帐号过期")
            case '43':
                raise SmsProviderException("IP地址限制")
            case '50':
                raise SmsProviderException("内容含有敏感词")
            case '51':
                raise SmsProviderException("手机号码不正确")
            case _:
                raise SmsProviderException(f"未知错误，错误代码：{response_text}")

    async def _send_sms(self, phone_number: str, code: str, code_ttl: int) -> bool:
        """
        发送短信验证码

        根据号码前缀自动选择接口：
        - +86 号码：剥离前缀，走国内接口 /sms
        - 其他号码：保持 E.164 格式，走国际接口 /wsms
        """
        ttl_minutes = str(code_ttl // 60)
        content = self.template.replace('{code}', code).replace('{time}', ttl_minutes)

        parsed = phonenumbers.parse(phone_number, None)
        if parsed.country_code == 86:
            url = 'https://api.smsbao.com/sms'
            m_param = str(parsed.national_number)
        else:
            url = 'https://api.smsbao.com/wsms'
            m_param = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)

        params = {
            'u': self.username,
            'p': self.password,
            'm': m_param,
            'c': content,
        }

        # 脱敏日志
        safe_params = params.copy()
        safe_params['p'] = '***' + self.password[-4:] if len(self.password) > 4 else '***'
        safe_params['c'] = content.replace(code, '****')
        l.debug(f"短信宝 SMS API 请求: url={url}, params={safe_params}")

        try:
            async with self.http_session.get(url, params=params) as response:
                resp_text = await response.text()
                l.info(f"短信宝 API 响应: {resp_text}, 手机号: {phone_number}")
                return self._handle_result(resp_text)
        except SmsProviderException:
            raise
        except Exception as e:
            l.exception(e)
            raise SmsInternalException(f"发送短信失败: {e}") from e

    async def _send_voice_code(self, phone_number: str, code: str) -> bool:
        """
        发送语音验证码

        短信宝语音接口仅支持中国大陆号码。
        """
        parsed = phonenumbers.parse(phone_number, None)
        if parsed.country_code != 86:
            raise SmsInternalException("短信宝语音验证码仅支持中国大陆号码")

        url = 'https://api.smsbao.com/voice'
        params = {
            'u': self.username,
            'p': self.password,
            'm': str(parsed.national_number),
            'c': code,
        }

        safe_params = params.copy()
        safe_params['p'] = '***' + self.password[-4:] if len(self.password) > 4 else '***'
        safe_params['c'] = '****'
        l.debug(f"短信宝 Voice API 请求: url={url}, params={safe_params}")

        try:
            async with self.http_session.get(url, params=params) as response:
                resp_text = await response.text()
                l.info(f"短信宝语音 API 响应: {resp_text}, 手机号: {phone_number}")
                return self._handle_result(resp_text)
        except SmsProviderException:
            raise
        except Exception as e:
            l.exception(e)
            raise SmsInternalException(f"发送语音验证码失败: {e}") from e


# ==================== DTO ====================

class SMSBaoProviderBaseDTO(SmsProviderBase):
    """SMSBao 基础字段"""

    username: Str64
    """短信宝账号"""

    template: Str256
    """短信模板"""


class SMSBaoProviderCreateRequest(SMSBaoProviderBaseDTO):
    """SMSBao 创建请求"""
    password: Str64
    """短信宝密码（MD5 加密后的）"""


class SMSBaoProviderUpdateRequest(SMSBaoProviderBaseDTO, all_fields_optional=True):
    """SMSBao 更新请求"""
    password: Str64 | None = None
    """短信宝密码"""


class SMSBaoProviderInfoResponse(SMSBaoProviderBaseDTO):
    """SMSBao 信息响应（不包含 password）"""
    pass
