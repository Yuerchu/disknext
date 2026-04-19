"""
S3 存储服务

使用 AWS Signature V4 签名的异步 S3 API 客户端。
从 Policy 配置中读取 S3 连接信息，提供文件上传/下载/删除及分片上传功能。

移植自 foxline-pro-backend-server 项目的 S3APIClient，
适配 DiskNext 现有的 Service 架构（与 LocalStorageService 平行）。
"""
import hashlib
import hmac
import xml.etree.ElementTree as ET
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import ClassVar, Literal
from urllib.parse import quote, urlencode
from uuid import UUID

import aiohttp
from yarl import URL
from loguru import logger as l

from sqlmodels.policy import Policy
from .exceptions import S3APIError, S3MultipartUploadError
from .naming_rule import NamingContext, NamingRuleParser


def _sign(key: bytes, msg: str) -> bytes:
    """HMAC-SHA256 签名"""
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


_NS_AWS = "http://s3.amazonaws.com/doc/2006-03-01/"


class S3StorageService:
    """
    S3 存储服务

    使用 AWS Signature V4 签名的异步 S3 API 客户端。
    从 Policy 配置中读取 S3 连接信息。

    使用示例::

        service = S3StorageService(policy, region='us-east-1')
        await service.upload_file('path/to/file.txt', b'content')
        data = await service.download_file('path/to/file.txt')
    """

    _http_session: ClassVar[aiohttp.ClientSession | None] = None

    def __init__(
            self,
            policy: Policy,
            region: str = 'us-east-1',
            is_path_style: bool = False,
    ):
        """
        :param policy: 存储策略（server=endpoint_url, bucket_name, access_key, secret_key）
        :param region: S3 区域
        :param is_path_style: 是否使用路径风格 URL
        """
        if not policy.server:
            raise S3APIError("S3 策略必须指定 server (endpoint URL)")
        if not policy.bucket_name:
            raise S3APIError("S3 策略必须指定 bucket_name")
        if not policy.access_key:
            raise S3APIError("S3 策略必须指定 access_key")
        if not policy.secret_key:
            raise S3APIError("S3 策略必须指定 secret_key")

        self._policy = policy
        self._endpoint_url = policy.server.rstrip("/")
        self._bucket_name = policy.bucket_name
        self._access_key = policy.access_key
        self._secret_key = policy.secret_key
        self._region = region
        self._is_path_style = is_path_style
        self._base_url = policy.base_url

        # 从 endpoint_url 提取 host
        self._host = self._endpoint_url.replace("https://", "").replace("http://", "").split("/")[0]

    # ==================== 工厂方法 ====================

    @classmethod
    def from_policy(cls, policy: Policy) -> 'S3StorageService':
        """
        根据 Policy 创建 S3StorageService

        :param policy: 存储策略（s3_region 和 s3_path_style 已在 Policy 表中）
        :return: S3StorageService 实例
        """
        return cls(policy, region=policy.s3_region, is_path_style=policy.s3_path_style)

    # ==================== HTTP Session 管理 ====================

    @classmethod
    async def initialize_session(cls) -> None:
        """初始化全局 aiohttp ClientSession"""
        if cls._http_session is None or cls._http_session.closed:
            cls._http_session = aiohttp.ClientSession()
            l.info("S3StorageService HTTP session 已初始化")

    @classmethod
    async def close_session(cls) -> None:
        """关闭全局 aiohttp ClientSession"""
        if cls._http_session and not cls._http_session.closed:
            await cls._http_session.close()
            cls._http_session = None
            l.info("S3StorageService HTTP session 已关闭")

    @classmethod
    def _get_session(cls) -> aiohttp.ClientSession:
        """获取 HTTP session"""
        if cls._http_session is None or cls._http_session.closed:
            # 懒初始化，以防 initialize_session 未被调用
            cls._http_session = aiohttp.ClientSession()
        return cls._http_session

    # ==================== AWS Signature V4 签名 ====================

    def _get_signature_key(self, date_stamp: str) -> bytes:
        """生成 AWS Signature V4 签名密钥"""
        k_date = _sign(f"AWS4{self._secret_key}".encode(), date_stamp)
        k_region = _sign(k_date, self._region)
        k_service = _sign(k_region, "s3")
        return _sign(k_service, "aws4_request")

    def _create_authorization_header(
            self,
            method: str,
            uri: str,
            query_string: str,
            headers: dict[str, str],
            payload_hash: str,
            amz_date: str,
            date_stamp: str,
    ) -> str:
        """创建 AWS Signature V4 授权头"""
        signed_headers = ";".join(sorted(k.lower() for k in headers.keys()))
        canonical_headers = "".join(
            f"{k.lower()}:{v.strip()}\n" for k, v in sorted(headers.items())
        )
        canonical_request = (
            f"{method}\n{uri}\n{query_string}\n{canonical_headers}\n"
            f"{signed_headers}\n{payload_hash}"
        )

        algorithm = "AWS4-HMAC-SHA256"
        credential_scope = f"{date_stamp}/{self._region}/s3/aws4_request"
        string_to_sign = (
            f"{algorithm}\n{amz_date}\n{credential_scope}\n"
            f"{hashlib.sha256(canonical_request.encode()).hexdigest()}"
        )

        signing_key = self._get_signature_key(date_stamp)
        signature = hmac.new(
            signing_key, string_to_sign.encode(), hashlib.sha256
        ).hexdigest()

        return (
            f"{algorithm} Credential={self._access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )

    def _build_headers(
            self,
            method: str,
            uri: str,
            query_string: str = "",
            payload: bytes = b"",
            content_type: str | None = None,
            extra_headers: dict[str, str] | None = None,
            payload_hash: str | None = None,
            host: str | None = None,
    ) -> dict[str, str]:
        """
        构建包含 AWS V4 签名的完整请求头

        :param method: HTTP 方法
        :param uri: 请求 URI
        :param query_string: 查询字符串
        :param payload: 请求体字节（用于计算哈希）
        :param content_type: Content-Type
        :param extra_headers: 额外请求头
        :param payload_hash: 预计算的 payload 哈希，流式上传时传 "UNSIGNED-PAYLOAD"
        :param host: Host 头（默认使用 self._host）
        """
        now_utc = datetime.now(timezone.utc)
        amz_date = now_utc.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now_utc.strftime("%Y%m%d")

        if payload_hash is None:
            payload_hash = hashlib.sha256(payload).hexdigest()

        effective_host = host or self._host

        headers: dict[str, str] = {
            "Host": effective_host,
            "X-Amz-Date": amz_date,
            "X-Amz-Content-Sha256": payload_hash,
        }
        if content_type:
            headers["Content-Type"] = content_type
        if extra_headers:
            headers.update(extra_headers)

        authorization = self._create_authorization_header(
            method, uri, query_string, headers, payload_hash, amz_date, date_stamp
        )
        headers["Authorization"] = authorization
        return headers

    # ==================== 内部请求方法 ====================

    def _build_uri(self, key: str | None = None) -> str:
        """
        构建请求 URI

        按 AWS S3 Signature V4 规范对路径进行 URI 编码（S3 仅需一次）。
        斜杠作为路径分隔符保留不编码。
        """
        if self._is_path_style:
            if key:
                return f"/{self._bucket_name}/{quote(key, safe='/')}"
            return f"/{self._bucket_name}"
        else:
            if key:
                return f"/{quote(key, safe='/')}"
            return "/"

    def _build_url(self, uri: str, query_string: str = "") -> str:
        """构建完整请求 URL"""
        if self._is_path_style:
            base = self._endpoint_url
        else:
            # 虚拟主机风格：bucket.endpoint
            protocol = "https://" if self._endpoint_url.startswith("https://") else "http://"
            base = f"{protocol}{self._bucket_name}.{self._host}"

        url = f"{base}{uri}"
        if query_string:
            url = f"{url}?{query_string}"
        return url

    def _get_effective_host(self) -> str:
        """获取实际请求的 Host 头"""
        if self._is_path_style:
            return self._host
        return f"{self._bucket_name}.{self._host}"

    async def _request(
            self,
            method: str,
            key: str | None = None,
            query_params: dict[str, str] | None = None,
            payload: bytes = b"",
            content_type: str | None = None,
            extra_headers: dict[str, str] | None = None,
    ) -> aiohttp.ClientResponse:
        """发送签名请求"""
        uri = self._build_uri(key)
        query_string = urlencode(sorted(query_params.items())) if query_params else ""
        effective_host = self._get_effective_host()

        headers = self._build_headers(
            method, uri, query_string, payload, content_type,
            extra_headers, host=effective_host,
        )

        url = self._build_url(uri, query_string)

        try:
            response = await self._get_session().request(
                method, URL(url, encoded=True),
                headers=headers, data=payload if payload else None,
            )
            return response
        except Exception as e:
            raise S3APIError(f"S3 请求失败: {method} {url}: {e}") from e

    async def _request_streaming(
            self,
            method: str,
            key: str,
            data_stream: AsyncIterator[bytes],
            content_length: int,
            content_type: str | None = None,
    ) -> aiohttp.ClientResponse:
        """
        发送流式签名请求（大文件上传）

        使用 UNSIGNED-PAYLOAD 作为 payload hash。
        """
        uri = self._build_uri(key)
        effective_host = self._get_effective_host()

        headers = self._build_headers(
            method,
            uri,
            query_string="",
            content_type=content_type,
            extra_headers={"Content-Length": str(content_length)},
            payload_hash="UNSIGNED-PAYLOAD",
            host=effective_host,
        )

        url = self._build_url(uri)

        try:
            response = await self._get_session().request(
                method, URL(url, encoded=True),
                headers=headers, data=data_stream,
            )
            return response
        except Exception as e:
            raise S3APIError(f"S3 流式请求失败: {method} {url}: {e}") from e

    # ==================== 文件操作 ====================

    async def upload_file(
            self,
            key: str,
            data: bytes,
            content_type: str = 'application/octet-stream',
    ) -> None:
        """
        上传文件

        :param key: S3 对象键
        :param data: 文件内容
        :param content_type: MIME 类型
        """
        async with await self._request(
            "PUT", key=key, payload=data, content_type=content_type,
        ) as response:
            if response.status not in (200, 201):
                body = await response.text()
                raise S3APIError(
                    f"上传失败: {self._bucket_name}/{key}, "
                    f"状态: {response.status}, {body}"
                )
            l.debug(f"S3 上传成功: {self._bucket_name}/{key}")

    async def upload_file_streaming(
            self,
            key: str,
            data_stream: AsyncIterator[bytes],
            content_length: int,
            content_type: str | None = None,
    ) -> None:
        """
        流式上传文件（大文件，避免全部加载到内存）

        :param key: S3 对象键
        :param data_stream: 异步字节流迭代器
        :param content_length: 数据总长度（必须准确）
        :param content_type: MIME 类型
        """
        async with await self._request_streaming(
            "PUT", key=key, data_stream=data_stream,
            content_length=content_length, content_type=content_type,
        ) as response:
            if response.status not in (200, 201):
                body = await response.text()
                raise S3APIError(
                    f"流式上传失败: {self._bucket_name}/{key}, "
                    f"状态: {response.status}, {body}"
                )
            l.debug(f"S3 流式上传成功: {self._bucket_name}/{key}, 大小: {content_length}")

    async def download_file(self, key: str) -> bytes:
        """
        下载文件

        :param key: S3 对象键
        :return: 文件内容
        """
        async with await self._request("GET", key=key) as response:
            if response.status != 200:
                body = await response.text()
                raise S3APIError(
                    f"下载失败: {self._bucket_name}/{key}, "
                    f"状态: {response.status}, {body}"
                )
            data = await response.read()
            l.debug(f"S3 下载成功: {self._bucket_name}/{key}, 大小: {len(data)}")
            return data

    async def delete_file(self, key: str) -> None:
        """
        删除文件

        :param key: S3 对象键
        """
        async with await self._request("DELETE", key=key) as response:
            if response.status in (200, 204):
                l.debug(f"S3 删除成功: {self._bucket_name}/{key}")
            else:
                body = await response.text()
                raise S3APIError(
                    f"删除失败: {self._bucket_name}/{key}, "
                    f"状态: {response.status}, {body}"
                )

    async def file_exists(self, key: str) -> bool:
        """
        检查文件是否存在

        :param key: S3 对象键
        :return: 是否存在
        """
        async with await self._request("HEAD", key=key) as response:
            if response.status == 200:
                return True
            elif response.status == 404:
                return False
            else:
                raise S3APIError(
                    f"检查文件存在性失败: {self._bucket_name}/{key}, 状态: {response.status}"
                )

    async def get_file_size(self, key: str) -> int:
        """
        获取文件大小

        :param key: S3 对象键
        :return: 文件大小（字节）
        """
        async with await self._request("HEAD", key=key) as response:
            if response.status != 200:
                raise S3APIError(
                    f"获取文件信息失败: {self._bucket_name}/{key}, 状态: {response.status}"
                )
            return int(response.headers.get("Content-Length", 0))

    # ==================== Multipart Upload ====================

    async def create_multipart_upload(
            self,
            key: str,
            content_type: str = 'application/octet-stream',
    ) -> str:
        """
        创建分片上传任务

        :param key: S3 对象键
        :param content_type: MIME 类型
        :return: Upload ID
        """
        async with await self._request(
            "POST",
            key=key,
            query_params={"uploads": ""},
            content_type=content_type,
        ) as response:
            if response.status != 200:
                body = await response.text()
                raise S3MultipartUploadError(
                    f"创建分片上传失败: {self._bucket_name}/{key}, "
                    f"状态: {response.status}, {body}"
                )

            body = await response.text()
            root = ET.fromstring(body)

            # 查找 UploadId 元素（支持命名空间）
            upload_id_elem = root.find("UploadId")
            if upload_id_elem is None:
                upload_id_elem = root.find(f"{{{_NS_AWS}}}UploadId")
            if upload_id_elem is None or not upload_id_elem.text:
                raise S3MultipartUploadError(
                    f"创建分片上传响应中未找到 UploadId: {body}"
                )

            upload_id = upload_id_elem.text
            l.debug(f"S3 分片上传已创建: {self._bucket_name}/{key}, upload_id={upload_id}")
            return upload_id

    async def upload_part(
            self,
            key: str,
            upload_id: str,
            part_number: int,
            data: bytes,
    ) -> str:
        """
        上传单个分片

        :param key: S3 对象键
        :param upload_id: 分片上传 ID
        :param part_number: 分片编号（从 1 开始）
        :param data: 分片数据
        :return: ETag
        """
        async with await self._request(
            "PUT",
            key=key,
            query_params={
                "partNumber": str(part_number),
                "uploadId": upload_id,
            },
            payload=data,
        ) as response:
            if response.status != 200:
                body = await response.text()
                raise S3MultipartUploadError(
                    f"上传分片失败: {self._bucket_name}/{key}, "
                    f"part={part_number}, 状态: {response.status}, {body}"
                )

            etag = response.headers.get("ETag", "").strip('"')
            l.debug(
                f"S3 分片上传成功: {self._bucket_name}/{key}, "
                f"part={part_number}, etag={etag}"
            )
            return etag

    async def complete_multipart_upload(
            self,
            key: str,
            upload_id: str,
            parts: list[tuple[int, str]],
    ) -> None:
        """
        完成分片上传

        :param key: S3 对象键
        :param upload_id: 分片上传 ID
        :param parts: 分片列表 [(part_number, etag)]
        """
        # 按 part_number 排序
        parts_sorted = sorted(parts, key=lambda p: p[0])

        # 构建 CompleteMultipartUpload XML
        xml_parts = ''.join(
            f"<Part><PartNumber>{pn}</PartNumber><ETag>{etag}</ETag></Part>"
            for pn, etag in parts_sorted
        )
        payload = f'<?xml version="1.0" encoding="UTF-8"?><CompleteMultipartUpload>{xml_parts}</CompleteMultipartUpload>'
        payload_bytes = payload.encode('utf-8')

        async with await self._request(
            "POST",
            key=key,
            query_params={"uploadId": upload_id},
            payload=payload_bytes,
            content_type="application/xml",
        ) as response:
            if response.status != 200:
                body = await response.text()
                raise S3MultipartUploadError(
                    f"完成分片上传失败: {self._bucket_name}/{key}, "
                    f"状态: {response.status}, {body}"
                )
            l.info(
                f"S3 分片上传已完成: {self._bucket_name}/{key}, "
                f"共 {len(parts)} 个分片"
            )

    async def abort_multipart_upload(self, key: str, upload_id: str) -> None:
        """
        取消分片上传

        :param key: S3 对象键
        :param upload_id: 分片上传 ID
        """
        async with await self._request(
            "DELETE",
            key=key,
            query_params={"uploadId": upload_id},
        ) as response:
            if response.status in (200, 204):
                l.debug(f"S3 分片上传已取消: {self._bucket_name}/{key}")
            else:
                body = await response.text()
                l.warning(
                    f"取消分片上传失败: {self._bucket_name}/{key}, "
                    f"状态: {response.status}, {body}"
                )

    # ==================== 预签名 URL ====================

    def generate_presigned_url(
            self,
            key: str,
            method: Literal['GET', 'PUT'] = 'GET',
            expires_in: int = 3600,
            filename: str | None = None,
    ) -> str:
        """
        生成 S3 预签名 URL（AWS Signature V4 Query String）

        :param key: S3 对象键
        :param method: HTTP 方法（GET 下载，PUT 上传）
        :param expires_in: URL 有效期（秒）
        :param filename: 文件名（GET 请求时设置 Content-Disposition）
        :return: 预签名 URL
        """
        current_time = datetime.now(timezone.utc)
        amz_date = current_time.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = current_time.strftime("%Y%m%d")

        credential_scope = f"{date_stamp}/{self._region}/s3/aws4_request"
        credential = f"{self._access_key}/{credential_scope}"

        uri = self._build_uri(key)
        effective_host = self._get_effective_host()

        query_params: dict[str, str] = {
            'X-Amz-Algorithm': 'AWS4-HMAC-SHA256',
            'X-Amz-Credential': credential,
            'X-Amz-Date': amz_date,
            'X-Amz-Expires': str(expires_in),
            'X-Amz-SignedHeaders': 'host',
        }

        # GET 请求时添加 Content-Disposition
        if method == "GET" and filename:
            encoded_filename = quote(filename, safe='')
            query_params['response-content-disposition'] = (
                f"attachment; filename*=UTF-8''{encoded_filename}"
            )

        canonical_query_string = "&".join(
            f"{quote(k, safe='')}={quote(v, safe='')}"
            for k, v in sorted(query_params.items())
        )

        canonical_headers = f"host:{effective_host}\n"
        signed_headers = "host"
        payload_hash = "UNSIGNED-PAYLOAD"

        canonical_request = (
            f"{method}\n"
            f"{uri}\n"
            f"{canonical_query_string}\n"
            f"{canonical_headers}\n"
            f"{signed_headers}\n"
            f"{payload_hash}"
        )

        algorithm = "AWS4-HMAC-SHA256"
        string_to_sign = (
            f"{algorithm}\n"
            f"{amz_date}\n"
            f"{credential_scope}\n"
            f"{hashlib.sha256(canonical_request.encode()).hexdigest()}"
        )

        signing_key = self._get_signature_key(date_stamp)
        signature = hmac.new(
            signing_key, string_to_sign.encode(), hashlib.sha256
        ).hexdigest()

        base_url = self._build_url(uri)
        return (
            f"{base_url}?"
            f"{canonical_query_string}&"
            f"X-Amz-Signature={signature}"
        )

    # ==================== 路径生成 ====================

    async def generate_file_path(
            self,
            user_id: UUID,
            original_filename: str,
    ) -> tuple[str, str, str]:
        """
        根据命名规则生成 S3 文件存储路径

        与 LocalStorageService.generate_file_path 接口一致。

        :param user_id: 用户UUID
        :param original_filename: 原始文件名
        :return: (相对目录路径, 存储文件名, 完整存储路径)
        """
        context = NamingContext(
            user_id=user_id,
            original_filename=original_filename,
        )

        # 解析目录规则
        dir_path = ""
        if self._policy.dir_name_rule:
            dir_path = NamingRuleParser.parse(self._policy.dir_name_rule, context)

        # 解析文件名规则
        if self._policy.auto_rename and self._policy.file_name_rule:
            storage_name = NamingRuleParser.parse(self._policy.file_name_rule, context)
            # 确保有扩展名
            if '.' in original_filename and '.' not in storage_name:
                ext = original_filename.rsplit('.', 1)[1]
                storage_name = f"{storage_name}.{ext}"
        else:
            storage_name = original_filename

        # S3 不需要创建目录，直接拼接路径
        if dir_path:
            storage_path = f"{dir_path}/{storage_name}"
        else:
            storage_path = storage_name

        return dir_path, storage_name, storage_path

    # ==================== StorageHandler 协议别名 ====================

    write = upload_file
    read = download_file
    delete = delete_file
    exists = file_exists
    generate_path = generate_file_path

    async def write_chunk(self, path: str, content: bytes, offset: int) -> int:
        """S3 不支持随机写入，分片上传请使用 multipart API"""
        raise NotImplementedError("S3 不支持 write_chunk，请使用 create_multipart_upload + upload_part")

    async def create_empty(self, path: str) -> None:
        """通过上传空内容创建空文件"""
        await self.upload_file(path, b'')

    def get_relative_path(self, full_path: str) -> str:
        """S3 路径本身就是相对路径"""
        return full_path
