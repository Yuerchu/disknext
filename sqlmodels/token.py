from datetime import datetime

from sqlmodel_ext import SQLModelBase

from .model_base import ResponseBase


class AccessTokenBase(SQLModelBase):
    """访问令牌响应 DTO"""

    access_expires: datetime
    """访问令牌过期时间"""

    access_token: str
    """访问令牌"""


class RefreshTokenBase(SQLModelBase):
    """刷新令牌响应DTO"""

    refresh_expires: datetime
    """刷新令牌过期时间"""

    refresh_token: str
    """刷新令牌"""


class TokenResponse(ResponseBase, AccessTokenBase, RefreshTokenBase):
    """令牌响应 DTO"""
