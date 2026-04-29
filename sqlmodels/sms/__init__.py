"""
短信提供商模块

使用联表继承实现多态短信提供商配置。

架构：
    SmsProvider (抽象基类，有自己的表)
    ├── SMSBaoProvider (短信宝实现)
    └── TencentCloudSMSProvider (腾讯云短信实现)

异常：
    SmsException (异常基类)
    ├── SmsProviderException (上游 API 错误)
    ├── SmsRateLimitException (频率限制错误)
    ├── SmsInternalException (内部非预期错误)
    └── SmsCodeInvalidException (验证码无效)
"""
from .base import (
    SmsProvider,
    SmsProviderBase,
    SmsException,
    SmsProviderException,
    SmsRateLimitException,
    SmsInternalException,
    SmsCodeInvalidException,
    SmsCodeTypeEnum,
    SmsCodeReasonEnum,
    SendSmsCodeRequest,
)
from .smsbao import (
    SMSBaoProvider,
    SMSBaoProviderBaseDTO,
    SMSBaoProviderCreateRequest,
    SMSBaoProviderUpdateRequest,
    SMSBaoProviderInfoResponse,
)
from .tencent_sms import (
    TencentCloudSMSProvider,
    TencentCloudSMSProviderBaseDTO,
    TencentCloudSMSProviderCreateRequest,
    TencentCloudSMSProviderUpdateRequest,
    TencentCloudSMSProviderInfoResponse,
    TencentSMSRegionEnum,
)
