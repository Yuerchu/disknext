"""GitHub OAuth2.0 认证实现"""
from typing import TYPE_CHECKING

from pydantic import BaseModel
from . import AccessTokenBase, OAuthBase, OAuthUserInfoResponse

if TYPE_CHECKING:
    from . import OAuthUserData


class GithubAccessToken(AccessTokenBase):
    """GitHub 访问令牌响应"""
    token_type: str
    """令牌类型"""
    scope: str
    """授权范围"""


class GithubUserData(BaseModel):
    """GitHub 用户数据"""
    login: str
    """用户名"""
    id: int
    """用户 ID"""
    node_id: str
    """节点 ID"""
    avatar_url: str
    """头像 URL"""
    gravatar_id: str | None
    """Gravatar ID"""
    url: str
    """API URL"""
    html_url: str
    """主页 URL"""
    followers_url: str
    """粉丝列表 URL"""
    following_url: str
    """关注列表 URL"""
    gists_url: str
    """Gists 列表 URL"""
    starred_url: str
    """星标列表 URL"""
    subscriptions_url: str
    """订阅列表 URL"""
    organizations_url: str
    """组织列表 URL"""
    repos_url: str
    """仓库列表 URL"""
    events_url: str
    """事件列表 URL"""
    received_events_url: str
    """接收的事件列表 URL"""
    type: str
    """用户类型"""
    site_admin: bool
    """是否为站点管理员"""
    name: str | None
    """显示名称"""
    company: str | None
    """公司"""
    blog: str | None
    """博客"""
    location: str | None
    """位置"""
    email: str | None
    """邮箱"""
    hireable: bool | None
    """是否可雇佣"""
    bio: str | None
    """个人简介"""
    twitter_username: str | None
    """Twitter 用户名"""
    public_repos: int
    """公开仓库数"""
    public_gists: int
    """公开 Gists 数"""
    followers: int
    """粉丝数"""
    following: int
    """关注数"""
    created_at: str
    """创建时间（ISO 8601 格式）"""
    updated_at: str
    """更新时间（ISO 8601 格式）"""


class GithubUserInfoResponse(BaseModel):
    """GitHub 用户信息响应"""
    code: str
    """状态码"""
    user_data: GithubUserData
    """用户数据"""


class GithubOAuth(OAuthBase):
    """GitHub OAuth2.0 客户端"""

    access_token_url = "https://github.com/login/oauth/access_token"
    """获取 Access Token 的 API 地址"""

    user_info_url = "https://api.github.com/user"
    """获取用户信息的 API 地址"""

    http_method = "POST"
    """获取 token 的 HTTP 方法"""

    def _parse_token_response(self, data: dict) -> GithubAccessToken:
        """解析 GitHub token 响应"""
        return GithubAccessToken(
            access_token=data.get('access_token'),
            token_type=data.get('token_type'),
            scope=data.get('scope'),
        )

    def _build_user_info_headers(self, access_token: str) -> dict:
        """构建 GitHub 用户信息请求头"""
        return {
            'accept': 'application/json',
            'Authorization': f'token {access_token}',
        }

    def _parse_user_response(self, data: dict) -> GithubUserInfoResponse:
        """解析 GitHub 用户信息响应"""
        return GithubUserInfoResponse(
            code='0' if data.get('login') else '1',
            user_data=GithubUserData(**data),
        )
