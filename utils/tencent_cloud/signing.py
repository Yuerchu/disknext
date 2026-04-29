"""
腾讯云 TC3-HMAC-SHA256 签名 Mixin

提供统一的 API 签名和请求方法，可被任何腾讯云服务类复用。
支持的产品包括但不限于：VOD、SMS、Hunyuan、COS 等。

使用方法::

    class MyTencentService(TencentCloudSigningMixin, ...):
        secret_id: str
        secret_key: str
        ...

    # 在方法中调用
    headers = self._build_tencent_headers(host, service, version, action, payload_str)
    resp = await self._tencent_request(host, service, version, action, payload)

注意：使用此 Mixin 的类必须：
    1. 有 secret_id 和 secret_key 属性
    2. 有 http_session 属性（通过 AioHttpClientSessionClassVarMixin）
"""
import hashlib
import hmac
import time
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

import orjson
from loguru import logger as l

from .exceptions import TencentCloudException, TencentCloudProhibitedContentException


@runtime_checkable
class TencentCloudCredentials(Protocol):
    """腾讯云凭证协议"""
    secret_id: str
    secret_key: str


class TencentCloudSigningMixin:
    """
    腾讯云 TC3-HMAC-SHA256 签名 Mixin

    提供统一的签名和请求方法，可被多个腾讯云服务类复用。

    要求：
    - 类必须有 secret_id 和 secret_key 属性
    - 类必须有 http_session 属性（aiohttp ClientSession）
    """

    # 这些属性由具体类提供：
    # - secret_id: str
    # - secret_key: str
    # - http_session: aiohttp.ClientSession
    # 注意：不在这里定义类型注解和属性，避免 SQLModel 把它们当作字段，
    # 也避免覆盖 AioHttpClientSessionClassVarMixin 提供的 http_session

    def _tencent_sign(self, key: bytes, msg: str) -> bytes:
        """
        HMAC-SHA256 签名

        :param key: 签名密钥
        :param msg: 待签名消息
        :returns: 签名结果
        """
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    def _build_tencent_headers(
        self,
        host: str,
        service: str,
        version: str,
        action: str,
        payload: str,
    ) -> dict[str, str]:
        """
        构建腾讯云 API 请求头，包含 TC3-HMAC-SHA256 签名

        :param host: 服务域名（如 sms.tencentcloudapi.com）
        :param service: 服务名（如 sms）
        :param version: API 版本（如 2021-01-11）
        :param action: API 操作名称（如 SendSms）
        :param payload: 请求体 JSON 字符串
        :returns: 完整的请求头字典
        """
        algorithm = "TC3-HMAC-SHA256"
        timestamp = int(time.time())
        date = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")

        # 步骤1: 拼接规范请求串
        http_request_method = "POST"
        canonical_uri = "/"
        canonical_querystring = ""
        ct = "application/json; charset=utf-8"
        canonical_headers = f"content-type:{ct}\nhost:{host}\nx-tc-action:{action.lower()}\n"
        signed_headers = "content-type;host;x-tc-action"
        hashed_request_payload = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        canonical_request = (
            http_request_method + "\n" +
            canonical_uri + "\n" +
            canonical_querystring + "\n" +
            canonical_headers + "\n" +
            signed_headers + "\n" +
            hashed_request_payload
        )

        # 步骤2: 拼接待签名字符串
        credential_scope = f"{date}/{service}/tc3_request"
        hashed_canonical_request = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
        string_to_sign = (
            algorithm + "\n" +
            str(timestamp) + "\n" +
            credential_scope + "\n" +
            hashed_canonical_request
        )

        # 步骤3: 计算签名
        secret_date = self._tencent_sign(("TC3" + self.secret_key).encode("utf-8"), date)  # pyright: ignore[reportAttributeAccessIssue]  # Mixin: secret_key provided by concrete class
        secret_service = self._tencent_sign(secret_date, service)
        secret_signing = self._tencent_sign(secret_service, "tc3_request")
        signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        # 步骤4: 拼接 Authorization
        authorization = (
            f"{algorithm} "
            f"Credential={self.secret_id}/{credential_scope}, "  # pyright: ignore[reportAttributeAccessIssue]  # Mixin: secret_id provided by concrete class
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )

        # 步骤5: 构造请求头
        headers: dict[str, str] = {
            "Authorization": authorization,
            "Content-Type": ct,
            "Host": host,
            "X-TC-Action": action,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Version": version,
        }

        return headers

    async def _tencent_request(
        self,
        host: str,
        service: str,
        version: str,
        action: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        发送腾讯云 API 请求

        :param host: 服务域名
        :param service: 服务名
        :param version: API 版本
        :param action: API 操作名称
        :param payload: 请求体字典
        :returns: 响应数据（Response 内容）
        :raises TencentCloudException: API 请求失败
        :raises TencentCloudProhibitedContentException: 内容审核不通过
        """
        # 使用紧凑格式序列化
        payload_bytes = orjson.dumps(payload)
        payload_str = payload_bytes.decode("utf-8")
        headers = self._build_tencent_headers(host, service, version, action, payload_str)
        url = f"https://{host}"

        try:
            async with self.http_session.post(  # pyright: ignore[reportAttributeAccessIssue]  # Mixin: http_session provided by concrete class
                url,
                headers=headers,
                data=payload_bytes,
            ) as response:
                if response.status != 200:
                    error_msg = f"HTTP {response.status}"
                    l.error(f"腾讯云 API 请求失败: {action}, {error_msg}")
                    raise TencentCloudException(error_msg, status_code=response.status)

                data: dict[str, Any] = await response.json()
                l.debug(f"腾讯云 API 响应 {action}: {data}")

                if "Response" not in data:
                    raise TencentCloudException(f"响应格式异常: {data}")

                resp = data["Response"]

                # 检查错误
                if "Error" in resp:
                    error = resp["Error"]
                    error_code = error.get("Code", "Unknown")
                    error_msg = error.get("Message", "Unknown error")
                    request_id = resp.get("RequestId")

                    # 检查是否是内容违规错误
                    if "Prohibited" in error_code or "Sensitive" in error_code:
                        raise TencentCloudProhibitedContentException(
                            f"内容审核不通过: {error_msg}",
                            request_id=request_id,
                        )

                    raise TencentCloudException(
                        f"API 错误 [{error_code}]: {error_msg}",
                        request_id=request_id,
                    )

                return resp

        except TencentCloudException:
            raise
        except Exception as e:
            l.exception(f"腾讯云 API 请求异常: {action}")
            raise TencentCloudException("服务暂时不可用，请稍后重试") from e
