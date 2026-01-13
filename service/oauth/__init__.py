"""
OAuth2.0 认证模块

提供统一的 OAuth2.0 客户端基类，支持多种第三方登录平台。
"""
import abc
import aiohttp

from pydantic import BaseModel


# ==================== 共享数据模型 ====================

class AccessTokenBase(BaseModel):
    """访问令牌基类"""
    access_token: str
    """访问令牌"""


class OAuthUserData(BaseModel):
    """OAuth 用户数据通用 DTO"""
    openid: str
    """用户唯一标识（GitHub 为 id，QQ 为 openid）"""
    nickname: str | None
    """用户昵称"""
    avatar_url: str | None
    """头像 URL"""
    email: str | None
    """邮箱"""
    bio: str | None
    """个人简介"""


class OAuthUserInfoResponse(BaseModel):
    """OAuth 用户信息响应"""
    code: str
    """状态码"""
    openid: str
    """用户唯一标识"""
    user_data: OAuthUserData
    """用户数据"""


# ==================== OAuth2.0 抽象基类 ====================

class OAuthBase(abc.ABC):
    """
    OAuth2.0 客户端抽象基类

    子类需要定义以下类属性：
    - access_token_url: 获取 Access Token 的 API 地址
    - user_info_url: 获取用户信息的 API 地址
    - http_method: 获取 token 的 HTTP 方法（POST 或 GET）
    """

    # 子类必须定义的类属性
    access_token_url: str
    """获取 Access Token 的 API 地址"""

    user_info_url: str
    """获取用户信息的 API 地址"""

    http_method: str = "POST"
    """获取 token 的 HTTP 方法：POST 或 GET"""

    # 实例属性（构造函数传入）
    client_id: str
    client_secret: str

    def __init__(self, client_id: str, client_secret: str) -> None:
        """
        初始化 OAuth 客户端

        Args:
            client_id: 应用 client_id
            client_secret: 应用 client_secret
        """
        self.client_id = client_id
        self.client_secret = client_secret

    async def get_access_token(self, code: str, **kwargs) -> AccessTokenBase:
        """
        通过 Authorization Code 获取 Access Token

        Args:
            code: 授权码
            **kwargs: 额外参数（如 QQ 需要 redirect_uri）

        Returns:
            AccessTokenBase: 访问令牌
        """
        params = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': code,
        }
        params.update(kwargs)

        async with aiohttp.ClientSession() as session:
            if self.http_method == "POST":
                async with session.post(
                    url=self.access_token_url,
                    params=params,
                    headers={'accept': 'application/json'},
                ) as access_resp:
                    access_data = await access_resp.json()
                    return self._parse_token_response(access_data)
            else:
                async with session.get(
                    url=self.access_token_url,
                    params=params,
                ) as access_resp:
                    access_data = await access_resp.json()
                    return self._parse_token_response(access_data)

    async def get_user_info(
        self,
        access_token: str | AccessTokenBase,
        **kwargs
    ) -> OAuthUserInfoResponse:
        """
        获取用户信息

        Args:
            access_token: 访问令牌
            **kwargs: 额外参数（如 QQ 需要 app_id, openid）

        Returns:
            OAuthUserInfoResponse: 用户信息
        """
        if isinstance(access_token, AccessTokenBase):
            access_token = access_token.access_token

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url=self.user_info_url,
                params=self._build_user_info_params(access_token, **kwargs),
                headers=self._build_user_info_headers(access_token),
            ) as resp:
                user_data = await resp.json()
                return self._parse_user_response(user_data)

    # ==================== 钩子方法（子类可覆盖） ====================

    def _build_user_info_params(self, access_token: str, **kwargs) -> dict:
        """
        构建获取用户信息的请求参数

        Args:
            access_token: 访问令牌
            **kwargs: 额外参数

        Returns:
            dict: 请求参数
        """
        return {}

    def _build_user_info_headers(self, access_token: str) -> dict:
        """
        构建获取用户信息的请求头

        Args:
            access_token: 访问令牌

        Returns:
            dict: 请求头
        """
        return {
            'accept': 'application/json',
        }

    def _parse_token_response(self, data: dict) -> AccessTokenBase:
        """
        解析 token 响应

        Args:
            data: API 返回的数据

        Returns:
            AccessTokenBase: 访问令牌
        """
        return AccessTokenBase(access_token=data.get('access_token'))

    def _parse_user_response(self, data: dict) -> OAuthUserInfoResponse:
        """
        解析用户信息响应

        Args:
            data: API 返回的数据

        Returns:
            OAuthUserInfoResponse: 用户信息
        """
        return OAuthUserInfoResponse(
            code='0',
            openid='',
            user_data=OAuthUserData(openid=''),
        )


# ==================== 导出 ====================

from .github import GithubOAuth, GithubAccessToken, GithubUserData
from .qq import QQOAuth, QQAccessToken, QQOpenIDResponse, QQUserData

__all__ = [
    # 共享模型
    'AccessTokenBase',
    'OAuthUserData',
    'OAuthUserInfoResponse',
    'OAuthBase',

    # GitHub
    'GithubOAuth',
    'GithubAccessToken',
    'GithubUserData',

    # QQ
    'QQOAuth',
    'QQAccessToken',
    'QQOpenIDResponse',
    'QQUserData',
]
