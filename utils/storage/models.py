"""
存储驱动值对象

提供跨存储后端的统一数据传输对象：
- DownloadResult: 下载描述符，路由层转为 HTTP 响应
- UploadContext: 分片上传会话上下文
- ChunkResult: 单分片上传结果
"""
from enum import StrEnum

from starlette.responses import FileResponse, RedirectResponse, Response

from sqlmodel_ext import SQLModelBase


class DownloadKind(StrEnum):
    FILE_PATH = "file_path"
    """本地文件路径，路由层用 FileResponse 直接输出"""

    REDIRECT_URL = "redirect_url"
    """预签名 URL / CDN URL，路由层用 RedirectResponse 302 重定向"""


class DownloadResult(SQLModelBase):
    """下载描述符，由 StorageDriver.get_download_result() 返回"""

    kind: DownloadKind
    """下载方式"""

    file_path: str | None = None
    """本地文件路径（kind=FILE_PATH 时有值）"""

    redirect_url: str | None = None
    """重定向 URL（kind=REDIRECT_URL 时有值）"""

    filename: str
    """下载文件名（Content-Disposition）"""

    media_type: str = 'application/octet-stream'
    """MIME 类型"""

    def to_response(self) -> Response:
        """转为 Starlette HTTP 响应（路由层调用）"""
        if self.kind == DownloadKind.FILE_PATH:
            return FileResponse(
                path=self.file_path,
                filename=self.filename,
                media_type=self.media_type,
            )
        elif self.kind == DownloadKind.REDIRECT_URL:
            return RedirectResponse(url=self.redirect_url, status_code=302)
        raise ValueError(f"未知的下载类型: {self.kind}")


class UploadContext(SQLModelBase):
    """
    分片上传会话上下文

    在分片上传生命周期中跨请求传递状态。
    路由层负责将此对象序列化到 UploadSession 表并在后续请求中重建。
    """

    path: str
    """存储路径"""

    total_size: int
    """文件总大小（字节）"""

    chunk_size: int
    """分片大小（字节）"""

    s3_upload_id: str | None = None
    """S3 Multipart Upload ID（仅 S3 驱动填充）"""

    s3_part_etags: list[list[int | str]] = []
    """S3 分片 ETag 列表 [[part_number, etag], ...]（仅 S3 驱动填充）"""


class ChunkResult(SQLModelBase):
    """单分片上传结果"""

    bytes_written: int
    """写入的字节数"""

    etag: str | None = None
    """S3 分片 ETag（仅 S3 驱动返回）"""

    part_number: int | None = None
    """S3 分片编号（仅 S3 驱动返回）"""
