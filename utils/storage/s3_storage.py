"""
S3 存储驱动

使用 AWS Signature V4 签名的异步 S3 API 客户端。
从 Policy 配置中读取 S3 连接信息，提供文件上传/下载/删除及分片上传功能。
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

from .base import StorageDriver
from .exceptions import S3APIError, S3MultipartUploadError
from .models import ChunkResult, DownloadKind, DownloadResult, UploadContext


def _sign(key: bytes, msg: str) -> bytes:
    """HMAC-SHA256 签名"""
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


_NS_AWS = "http://s3.amazonaws.com/doc/2006-03-01/"


class S3StorageDriver(StorageDriver):
    """
    S3 存储驱动

    使用 AWS Signature V4 签名的异步 S3 API 客户端。
    从 Policy 配置中读取 S3 连接信息。

    使用示例::

        driver = S3StorageDriver(policy)
        await driver.write('path/to/file.txt', b'content')
        data = await driver.read('path/to/file.txt')
    """

    _http_session: ClassVar[aiohttp.ClientSession | None] = None

    def __init__(self, policy: Policy) -> None:
        super().__init__(policy)
        if not policy.server:
            raise S3APIError("S3 策略必须指定 server (endpoint URL)")
        if not policy.bucket_name:
            raise S3APIError("S3 策略必须指定 bucket_name")
        if not policy.access_key:
            raise S3APIError("S3 策略必须指定 access_key")
        if not policy.secret_key:
            raise S3APIError("S3 策略必须指定 secret_key")

        self._endpoint_url = policy.server.rstrip("/")
        self._bucket_name = policy.bucket_name
        self._access_key = policy.access_key
        self._secret_key = policy.secret_key
        self._region = policy.s3_region
        self._is_path_style = policy.s3_path_style
        self._base_url = policy.base_url
        self._host = self._endpoint_url.replace("https://", "").replace("http://", "").split("/")[0]

    # ==================== 能力声明 ====================

    @property
    def is_supports_presigned_url(self) -> bool:
        return True

    # ==================== 路径组装 ====================

    async def _assemble_path(self, dir_path: str, storage_name: str) -> str:
        """S3：/ 拼接，不创建目录"""
        if dir_path:
            return f"{dir_path}/{storage_name}"
        return storage_name

    # ==================== HTTP Session 管理（类级别） ====================

    @classmethod
    async def initialize_session(cls) -> None:
        """初始化全局 aiohttp ClientSession"""
        if cls._http_session is None or cls._http_session.closed:
            cls._http_session = aiohttp.ClientSession()
            l.info("S3StorageDriver HTTP session 已初始化")

    @classmethod
    async def close_session(cls) -> None:
        """关闭全局 aiohttp ClientSession"""
        if cls._http_session and not cls._http_session.closed:
            await cls._http_session.close()
            cls._http_session = None
            l.info("S3StorageDriver HTTP session 已关闭")

    @classmethod
    def _get_session(cls) -> aiohttp.ClientSession:
        """获取 HTTP session"""
        if cls._http_session is None or cls._http_session.closed:
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
        """构建包含 AWS V4 签名的完整请求头"""
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
        """构建请求 URI"""
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
        """发送流式签名请求（大文件上传）"""
        uri = self._build_uri(key)
        effective_host = self._get_effective_host()

        headers = self._build_headers(
            method, uri, query_string="",
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

    # ==================== 核心 I/O ====================

    async def write(self, path: str, content: bytes) -> int:
        """上传文件"""
        async with await self._request(
            "PUT", key=path, payload=content,
            content_type='application/octet-stream',
        ) as response:
            if response.status not in (200, 201):
                body = await response.text()
                raise S3APIError(
                    f"上传失败: {self._bucket_name}/{path}, "
                    f"状态: {response.status}, {body}"
                )
            l.debug(f"S3 上传成功: {self._bucket_name}/{path}")
        return len(content)

    async def read(self, path: str) -> bytes:
        """下载文件"""
        async with await self._request("GET", key=path) as response:
            if response.status != 200:
                body = await response.text()
                raise S3APIError(
                    f"下载失败: {self._bucket_name}/{path}, "
                    f"状态: {response.status}, {body}"
                )
            data = await response.read()
            l.debug(f"S3 下载成功: {self._bucket_name}/{path}, 大小: {len(data)}")
            return data

    async def delete(self, path: str) -> None:
        """删除文件"""
        async with await self._request("DELETE", key=path) as response:
            if response.status in (200, 204):
                l.debug(f"S3 删除成功: {self._bucket_name}/{path}")
            else:
                body = await response.text()
                raise S3APIError(
                    f"删除失败: {self._bucket_name}/{path}, "
                    f"状态: {response.status}, {body}"
                )

    async def exists(self, path: str) -> bool:
        """检查文件是否存在"""
        async with await self._request("HEAD", key=path) as response:
            if response.status == 200:
                return True
            elif response.status == 404:
                return False
            else:
                raise S3APIError(
                    f"检查文件存在性失败: {self._bucket_name}/{path}, 状态: {response.status}"
                )

    async def get_size(self, path: str) -> int:
        """获取文件大小"""
        async with await self._request("HEAD", key=path) as response:
            if response.status != 200:
                raise S3APIError(
                    f"获取文件信息失败: {self._bucket_name}/{path}, 状态: {response.status}"
                )
            return int(response.headers.get("Content-Length", 0))

    async def create_empty(self, path: str) -> None:
        """通过上传空内容创建空文件"""
        await self.write(path, b'')

    def get_relative_path(self, full_path: str) -> str:
        """S3 路径本身就是相对路径"""
        return full_path

    # ==================== 分片上传生命周期 ====================

    async def init_upload(
        self,
        path: str,
        total_size: int,
        chunk_size: int,
        content_type: str = 'application/octet-stream',
    ) -> UploadContext:
        """
        S3 分片上传初始化

        单分片不需要 multipart API，多分片则创建 multipart upload。
        """
        total_chunks = max(1, (total_size + chunk_size - 1) // chunk_size) if total_size > 0 else 1
        s3_upload_id: str | None = None

        if total_chunks > 1:
            s3_upload_id = await self._create_multipart_upload(path, content_type)

        return UploadContext(
            path=path,
            total_size=total_size,
            chunk_size=chunk_size,
            s3_upload_id=s3_upload_id,
        )

    async def upload_chunk(
        self,
        ctx: UploadContext,
        chunk_index: int,
        content: bytes,
    ) -> ChunkResult:
        """
        S3 分片上传

        单分片：直接 PUT 上传。
        多分片：调用 UploadPart API，返回 ETag。
        """
        if ctx.s3_upload_id is None:
            # 单分片：直接上传
            await self.write(ctx.path, content)
            return ChunkResult(bytes_written=len(content))

        # 多分片：UploadPart
        part_number = chunk_index + 1  # S3 part number 从 1 开始
        etag = await self._upload_part(ctx.path, ctx.s3_upload_id, part_number, content)
        ctx.s3_part_etags.append([part_number, etag])

        return ChunkResult(
            bytes_written=len(content),
            etag=etag,
            part_number=part_number,
        )

    async def complete_upload(self, ctx: UploadContext) -> None:
        """S3：完成 multipart upload"""
        if ctx.s3_upload_id and ctx.s3_part_etags:
            parts = [(int(pn), str(et)) for pn, et in ctx.s3_part_etags]
            await self._complete_multipart_upload(ctx.path, ctx.s3_upload_id, parts)

    async def abort_upload(self, ctx: UploadContext) -> None:
        """S3：取消 multipart upload 或删除已上传的单分片"""
        if ctx.s3_upload_id:
            await self._abort_multipart_upload(ctx.path, ctx.s3_upload_id)
        else:
            await self.delete(ctx.path)

    # ==================== 下载 ====================

    async def get_download_result(self, path: str, filename: str) -> DownloadResult:
        """S3：生成预签名 URL"""
        presigned_url = self.generate_presigned_url(path, method='GET', expires_in=3600, filename=filename)
        return DownloadResult(
            kind=DownloadKind.REDIRECT_URL,
            redirect_url=presigned_url,
            filename=filename,
        )

    async def get_source_link_result(self, path: str, filename: str) -> DownloadResult:
        """
        外链下载

        公有 + 有 base_url → 直接重定向到公开 URL。
        私有 → 预签名 URL。
        """
        is_private = self._policy.is_private
        base_url = self._policy.base_url

        if not is_private and base_url:
            redirect_url = f"{base_url.rstrip('/')}/{path}"
            return DownloadResult(
                kind=DownloadKind.REDIRECT_URL,
                redirect_url=redirect_url,
                filename=filename,
            )

        return await self.get_download_result(path, filename)

    # ==================== 生命周期管理 ====================

    async def ensure_base_directory(self) -> None:
        """S3 无目录概念，no-op"""

    async def move_to_trash(
        self,
        source_path: str,
        user_id: UUID,
        entry_id: UUID,
    ) -> str | None:
        """S3 无回收站概念，直接删除"""
        await self.delete(source_path)
        return None

    async def restore_from_trash(self, trash_path: str, restore_path: str) -> None:
        """S3 不支持回收站恢复"""
        raise NotImplementedError("S3 存储不支持从回收站恢复")

    async def empty_trash(self, user_id: UUID) -> int:
        """S3 无回收站，返回 0"""
        return 0

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
        :param method: HTTP 方法
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
            f"{method}\n{uri}\n{canonical_query_string}\n"
            f"{canonical_headers}\n{signed_headers}\n{payload_hash}"
        )

        algorithm = "AWS4-HMAC-SHA256"
        string_to_sign = (
            f"{algorithm}\n{amz_date}\n{credential_scope}\n"
            f"{hashlib.sha256(canonical_request.encode()).hexdigest()}"
        )

        signing_key = self._get_signature_key(date_stamp)
        signature = hmac.new(
            signing_key, string_to_sign.encode(), hashlib.sha256
        ).hexdigest()

        base_url = self._build_url(uri)
        return f"{base_url}?{canonical_query_string}&X-Amz-Signature={signature}"

    # ==================== 流式上传（公开方法，供需要流式传输的场景使用） ====================

    async def write_streaming(
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
                    f"流式上传失败: {self._bucket_name}/{key}, 状态: {response.status}, {body}"
                )
            l.debug(f"S3 流式上传成功: {self._bucket_name}/{key}, 大小: {content_length}")

    # ==================== S3 Multipart 内部方法 ====================

    async def _create_multipart_upload(
            self,
            key: str,
            content_type: str = 'application/octet-stream',
    ) -> str:
        """创建分片上传任务，返回 Upload ID"""
        async with await self._request(
            "POST", key=key,
            query_params={"uploads": ""},
            content_type=content_type,
        ) as response:
            if response.status != 200:
                body = await response.text()
                raise S3MultipartUploadError(
                    f"创建分片上传失败: {self._bucket_name}/{key}, 状态: {response.status}, {body}"
                )

            body = await response.text()
            root = ET.fromstring(body)

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

    async def _upload_part(
            self,
            key: str,
            upload_id: str,
            part_number: int,
            data: bytes,
    ) -> str:
        """上传单个分片，返回 ETag"""
        async with await self._request(
            "PUT", key=key,
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

    async def _complete_multipart_upload(
            self,
            key: str,
            upload_id: str,
            parts: list[tuple[int, str]],
    ) -> None:
        """完成分片上传"""
        parts_sorted = sorted(parts, key=lambda p: p[0])

        xml_parts = ''.join(
            f"<Part><PartNumber>{pn}</PartNumber><ETag>{etag}</ETag></Part>"
            for pn, etag in parts_sorted
        )
        payload = f'<?xml version="1.0" encoding="UTF-8"?><CompleteMultipartUpload>{xml_parts}</CompleteMultipartUpload>'
        payload_bytes = payload.encode('utf-8')

        async with await self._request(
            "POST", key=key,
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

    async def _abort_multipart_upload(self, key: str, upload_id: str) -> None:
        """取消分片上传"""
        async with await self._request(
            "DELETE", key=key,
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


# 向后兼容别名（Phase 5 删除）
S3StorageService = S3StorageDriver
