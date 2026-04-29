"""
腾讯云 API 通用异常类

适用于所有腾讯云产品（VOD、SMS、Hunyuan、COS 等）。
产品特有的异常应继承此模块中的基类，定义在各自的模块中。
"""


class TencentCloudException(Exception):
    """腾讯云 API 异常基类"""

    message: str
    request_id: str | None
    status_code: int | None

    def __init__(self, message: str, request_id: str | None = None, status_code: int | None = None):
        self.message = message
        self.request_id = request_id
        self.status_code = status_code
        super().__init__(message)


class TencentCloudProhibitedContentException(TencentCloudException):
    """腾讯云内容审核不通过"""
    pass
