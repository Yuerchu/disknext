"""
腾讯云短信验证码提供商

使用腾讯云 SMS API（TC3-HMAC-SHA256 签名方法 v3）发送短信验证码。

API 文档：
- 发送短信: https://cloud.tencent.com/document/product/382/55981
- 公共参数: https://cloud.tencent.com/document/api/382/52071
- 错误码: https://cloud.tencent.com/document/product/382/52075
"""
from enum import StrEnum
from typing import Annotated

import orjson
import phonenumbers
from loguru import logger as l
from pydantic import ValidationError
from sqlmodel import Field

from sqlmodel_ext import AutoPolymorphicIdentityMixin, ExtraIgnoreModelBase, Str64, Str256

from utils.tencent_cloud import TencentCloudSigningMixin, TencentCloudException

from .base import (
    SmsProvider,
    SmsProviderBase,
    SmsProviderException,
    SmsInternalException,
)


# ==================== 腾讯云 SMS API 响应模型 ====================

class TencentSMSSendStatus(ExtraIgnoreModelBase):
    """SendSms API 单条发送状态"""

    code: Annotated[str, Field(alias="Code")]
    """发送状态码（"Ok" 表示成功）"""

    message: Annotated[str, Field(alias="Message")]
    """状态描述"""

    serial_no: Annotated[str, Field(alias="SerialNo")] = ""
    """发送流水号"""

    phone_number: Annotated[str, Field(alias="PhoneNumber")] = ""
    """手机号"""

    fee: Annotated[int, Field(alias="Fee")] = 0
    """计费条数"""

    session_context: Annotated[str, Field(alias="SessionContext")] = ""
    """用户 Session 内容"""

    iso_code: Annotated[str, Field(alias="IsoCode")] = ""
    """国家/地区码"""


class TencentCloudAPIError(ExtraIgnoreModelBase):
    """腾讯云 API 通用错误"""

    code: Annotated[str, Field(alias="Code")]
    """错误码"""

    message: Annotated[str, Field(alias="Message")]
    """错误描述"""


class TencentSMSResponseInner(ExtraIgnoreModelBase):
    """
    SendSms API Response 内部数据

    腾讯云 API 结构：{"Response": {"SendStatusSet": [...], "Error": {...}, "RequestId": "..."}}
    """

    send_status_set: Annotated[list[TencentSMSSendStatus] | None, Field(alias="SendStatusSet")] = None
    """发送状态列表（成功时）"""

    error: Annotated[TencentCloudAPIError | None, Field(alias="Error")] = None
    """错误信息（失败时）"""

    request_id: Annotated[str, Field(alias="RequestId")] = ""
    """请求 ID"""


class TencentSMSAPIResponse(ExtraIgnoreModelBase):
    """腾讯云 SMS API 完整响应包装"""

    response: Annotated[TencentSMSResponseInner, Field(alias="Response")]
    """Response 内部数据"""


# ==================== 常量 ====================

TENCENT_SMS_HOST = "sms.tencentcloudapi.com"
"""腾讯云短信服务域名"""

TENCENT_SMS_SERVICE = "sms"
"""腾讯云短信服务名（用于签名）"""

TENCENT_SMS_VERSION = "2021-01-11"
"""腾讯云短信 API 版本"""


class TencentSMSRegionEnum(StrEnum):
    """
    腾讯云短信 API 支持的地域

    SMS 产品仅支持以下三个地域。
    """
    AP_BEIJING = "ap-beijing"
    """华北地区（北京）"""

    AP_GUANGZHOU = "ap-guangzhou"
    """华南地区（广州）"""

    AP_NANJING = "ap-nanjing"
    """华东地区（南京）"""


# ==================== 提供商实现 ====================

class TencentCloudSMSProvider(
    SmsProvider,
    TencentCloudSigningMixin,
    AutoPolymorphicIdentityMixin,
    table=True,
):
    """
    腾讯云短信验证码提供商

    通过 TencentCloudSigningMixin 复用 TC3-HMAC-SHA256 签名逻辑。
    """

    secret_id: Str256
    """腾讯云 SecretId"""

    secret_key: Str256
    """腾讯云 SecretKey"""

    sms_sdk_app_id: Str64
    """短信应用 SdkAppId（在短信控制台添加应用后生成）"""

    sign_name: Str64
    """短信签名内容（须已审核通过）"""

    template_id: Str64
    """短信模板 ID（须已审核通过，模板变量为验证码和有效期分钟数）"""

    region: TencentSMSRegionEnum = TencentSMSRegionEnum.AP_GUANGZHOU
    """API 地域"""

    async def _send_sms(self, phone_number: str, code: str, code_ttl: int) -> bool:
        """通过腾讯云 SMS API 发送短信验证码"""
        ttl_minutes = str(code_ttl // 60)

        e164_phone = phonenumbers.format_number(
            phonenumbers.parse(phone_number, None),
            phonenumbers.PhoneNumberFormat.E164,
        )
        payload: dict[str, str | list[str]] = {
            "PhoneNumberSet": [e164_phone],
            "SmsSdkAppId": self.sms_sdk_app_id,
            "SignName": self.sign_name,
            "TemplateId": self.template_id,
            "TemplateParamSet": [code, ttl_minutes],
        }

        l.debug(f"腾讯云 SMS 发送请求: phone={phone_number}, template={self.template_id}")

        try:
            resp = await self._tencent_sms_request("SendSms", payload)

            if not resp.send_status_set:
                raise SmsProviderException("腾讯云 SMS 响应缺少 SendStatusSet")

            status = resp.send_status_set[0]

            if status.code == "Ok":
                l.info(f"腾讯云 SMS 发送成功: phone={phone_number}, serial={status.serial_no}")
                return True

            l.error(f"腾讯云 SMS 发送失败: phone={phone_number}, code={status.code}, msg={status.message}")
            raise SmsProviderException(f"短信发送失败: {status.message}")

        except (SmsProviderException, SmsInternalException):
            raise
        except TencentCloudException as e:
            l.error(f"腾讯云 SMS API 异常: {e.message}")
            raise SmsProviderException(f"短信服务异常: {e.message}") from e
        except Exception as e:
            l.exception(f"腾讯云 SMS 发送异常: phone={phone_number}")
            raise SmsInternalException(f"发送短信失败: {e}") from e

    async def _send_voice_code(self, phone_number: str, code: str) -> bool:
        """腾讯云语音验证码（暂未实现）"""
        raise SmsInternalException("腾讯云语音验证码暂不支持")

    async def _tencent_sms_request(
        self,
        action: str,
        payload: dict[str, str | list[str]],
    ) -> TencentSMSResponseInner:
        """
        发送腾讯云 SMS API 请求（带 Region 头）

        SMS API 要求 X-TC-Region 头。
        """
        payload_bytes = orjson.dumps(payload)
        payload_str = payload_bytes.decode("utf-8")
        headers = self._build_tencent_headers(
            TENCENT_SMS_HOST, TENCENT_SMS_SERVICE, TENCENT_SMS_VERSION, action, payload_str,
        )
        headers["X-TC-Region"] = self.region
        url = f"https://{TENCENT_SMS_HOST}"

        try:
            async with self.http_session.post(
                url,
                headers=headers,
                data=payload_bytes,
            ) as response:
                if response.status != 200:
                    error_msg = f"HTTP {response.status}"
                    l.error(f"腾讯云 SMS API 请求失败: {action}, {error_msg}")
                    raise TencentCloudException(error_msg, status_code=response.status)

                data = await response.json()
                l.debug(f"腾讯云 SMS API 响应 {action}: {data}")

                api_resp = TencentSMSAPIResponse(**data)
                inner = api_resp.response

                if inner.error is not None:
                    raise TencentCloudException(
                        f"SMS API 错误 [{inner.error.code}]: {inner.error.message}",
                        request_id=inner.request_id or None,
                    )

                return inner

        except TencentCloudException:
            raise
        except ValidationError as e:
            raise TencentCloudException(f"SMS API 响应格式异常: {e}") from e
        except Exception as e:
            l.exception(f"腾讯云 SMS API 请求异常: {action}")
            raise TencentCloudException("短信服务暂时不可用，请稍后重试") from e


# ==================== DTO ====================

class TencentCloudSMSProviderBaseDTO(SmsProviderBase):
    """腾讯云 SMS 基础字段"""

    secret_id: Str256
    """腾讯云 SecretId"""

    secret_key: Str256
    """腾讯云 SecretKey"""

    sms_sdk_app_id: Str64
    """短信应用 SdkAppId"""

    sign_name: Str64
    """短信签名内容"""

    template_id: Str64
    """短信模板 ID"""

    region: TencentSMSRegionEnum = TencentSMSRegionEnum.AP_GUANGZHOU
    """API 地域"""


class TencentCloudSMSProviderCreateRequest(TencentCloudSMSProviderBaseDTO):
    """腾讯云 SMS 创建请求"""
    pass


class TencentCloudSMSProviderUpdateRequest(TencentCloudSMSProviderBaseDTO, all_fields_optional=True):
    """腾讯云 SMS 更新请求"""
    pass


class TencentCloudSMSProviderInfoResponse(TencentCloudSMSProviderBaseDTO):
    """腾讯云 SMS 信息响应"""
    pass
