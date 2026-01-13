"""QQ OAuth2.0 认证实现"""
import aiohttp

from pydantic import BaseModel
from . import AccessTokenBase, OAuthBase


class QQAccessToken(AccessTokenBase):
    """QQ 访问令牌响应"""
    expires_in: int
    """access token 的有效期，单位为秒"""
    refresh_token: str
    """用于刷新 access token 的令牌"""


class QQOpenIDResponse(BaseModel):
    """QQ OpenID 响应"""
    client_id: str
    """应用的 appid"""
    openid: str
    """用户的唯一标识"""


class QQUserData(BaseModel):
    """QQ 用户数据"""
    ret: int
    """返回码，0 表示成功"""
    msg: str
    """返回信息"""
    nickname: str | None
    """用户昵称"""
    gender: str | None
    """性别"""
    figureurl: str | None
    """头像 URL"""
    figureurl_1: str | None
    """头像 URL（大图）"""
    figureurl_2: str | None
    """头像 URL（更大图）"""
    figureurl_qq_1: str | None
    """QQ 头像 URL（大图）"""
    figureurl_qq_2: str | None
    """QQ 头像 URL（更大图）"""
    is_yellow_vip: str | None
    """是否黄钻用户"""
    vip: str | None
    """是否 VIP 用户"""
    yellow_vip_level: str | None
    """黄钻等级"""
    level: str | None
    """等级"""
    is_yellow_year_vip: str | None
    """是否年费黄钻"""


class QQUserInfoResponse(BaseModel):
    """QQ 用户信息响应"""
    code: str
    """状态码"""
    openid: str
    """用户 OpenID"""
    user_data: QQUserData
    """用户数据"""


class QQOAuth(OAuthBase):
    """QQ OAuth2.0 客户端"""

    access_token_url = "https://graph.qq.com/oauth2.0/token"
    """获取 Access Token 的 API 地址"""

    user_info_url = "https://graph.qq.com/user/get_user_info"
    """获取用户信息的 API 地址"""

    openid_url = "https://graph.qq.com/oauth2.0/me"
    """获取 OpenID 的 API 地址"""

    http_method = "GET"
    """获取 token 的 HTTP 方法"""

    async def get_access_token(self, code: str, redirect_uri: str) -> QQAccessToken:
        """
        通过 Authorization Code 获取 Access Token

        Args:
            code: 授权码
            redirect_uri: 与授权时传入的 redirect_uri 保持一致，需要 URLEncode

        Returns:
            QQAccessToken: 访问令牌

        文档:
            https://wiki.connect.qq.com/%E4%BD%BF%E7%94%A8authorization_code%E8%8E%B7%E5%8F%96access_token
        """
        params = {
            'grant_type': 'authorization_code',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': code,
            'redirect_uri': redirect_uri,
            'fmt': 'json',
            'need_openid': 1,
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url=self.access_token_url, params=params) as access_resp:
                access_data = await access_resp.json()
                return QQAccessToken(
                    access_token=access_data.get('access_token'),
                    expires_in=access_data.get('expires_in'),
                    refresh_token=access_data.get('refresh_token'),
                )

    async def get_openid(self, access_token: str) -> QQOpenIDResponse:
        """
        获取用户 OpenID

        注意：如果在 get_access_token 时传入了 need_openid=1，响应中已包含 openid，
        无需额外调用此接口。此函数用于单独获取 openid 的场景。

        Args:
            access_token: 访问令牌

        Returns:
            QQOpenIDResponse: 包含 client_id 和 openid

        文档:
            https://wiki.connect.qq.com/%E8%8E%B7%E5%8F%96%E7%94%A8%E6%88%B7openid%E7%9A%84oauth2.0%E6%8E%A5%E5%8F%A3
        """
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url=self.openid_url,
                params={
                    'access_token': access_token,
                    'fmt': 'json',
                },
            ) as resp:
                data = await resp.json()
                return QQOpenIDResponse(
                    client_id=data.get('client_id'),
                    openid=data.get('openid'),
                )

    def _build_user_info_params(self, access_token: str, **kwargs) -> dict:
        """构建 QQ 用户信息请求参数"""
        return {
            'access_token': access_token,
            'oauth_consumer_key': kwargs.get('app_id', self.client_id),
            'openid': kwargs.get('openid', ''),
        }

    def _parse_user_response(self, data: dict) -> QQUserInfoResponse:
        """解析 QQ 用户信息响应"""
        return QQUserInfoResponse(
            code='0' if data.get('ret') == 0 else str(data.get('ret')),
            openid=data.get('openid', ''),
            user_data=QQUserData(**data),
        )
