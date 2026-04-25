"""
WebDAV 认证控制器

实现 WsgiDAV 的 BaseDomainController 接口，使用 HTTP Basic Auth
通过 DiskNext 的 WebDAV 账户模型进行认证。

用户名格式: {email}/{webdav_account_name}
"""
import asyncio
from uuid import UUID

from loguru import logger as l
from wsgidav.dc.base_dc import BaseDomainController
from sqlmodel_ext import rel, cond

from routers.dav.provider import EventLoopRef, _get_session
from utils.redis.webdav_auth_cache import WebDAVAuthCache
from sqlmodels.user import User, UserStatus
from sqlmodels.webdav import WebDAV
from utils.password.pwd import Password, PasswordStatus


async def _authenticate(
    email: str,
    account_name: str,
    password: str,
) -> tuple[UUID, UUID] | None:
    """
    异步认证 WebDAV 用户。

    :param email: 用户邮箱
    :param account_name: WebDAV 账户名
    :param password: 明文密码
    :return: (user_id, webdav_id) 或 None
    """
    # 1. 查缓存
    cached = await WebDAVAuthCache.get(email, account_name, password)
    if cached is not None:
        return cached

    # 2. 缓存未命中，查库验证
    async with _get_session() as session:
        user = await User.get(session, cond(User.email == email), load=rel(User.group))
        if not user:
            return None
        if user.status != UserStatus.ACTIVE:
            return None
        if not user.group.web_dav_enabled:
            return None

        account = await WebDAV.get(
            session,
            cond(WebDAV.name == account_name) & cond(WebDAV.user_id == user.id),
        )
        if not account:
            return None

        status = Password.verify(account.password, password)
        if status == PasswordStatus.INVALID:
            return None

        user_id: UUID = user.id
        webdav_id: UUID | None = account.id
        
        if not webdav_id:
            raise ValueError("WebDAV 账户 ID 不能为空")

    # 3. 写入缓存
    await WebDAVAuthCache.set(email, account_name, password, user_id, webdav_id)

    return user_id, webdav_id


class DiskNextDomainController(BaseDomainController):
    """
    DiskNext WebDAV 认证控制器

    用户名格式: {email}/{webdav_account_name}
    密码: WebDAV 账户密码（创建账户时设置）
    """

    def __init__(self, wsgidav_app: object, config: dict[str, object]) -> None:
        super().__init__(wsgidav_app, config)

    def get_domain_realm(self, path_info: str, environ: dict[str, object]) -> str:
        """返回 realm 名称"""
        return "DiskNext WebDAV"

    def require_authentication(self, realm: str, environ: dict[str, object]) -> bool:
        """所有请求都需要认证"""
        return True

    def is_share_anonymous(self, path_info: str) -> bool:
        """不支持匿名访问"""
        return False

    def supports_http_digest_auth(self) -> bool:
        """不支持 Digest 认证（密码存的是 Argon2 哈希，无法反推）"""
        return False

    def basic_auth_user(
        self,
        realm: str,
        user_name: str,
        password: str,
        environ: dict[str, object],
    ) -> bool:
        """
        HTTP Basic Auth 认证。

        用户名格式: {email}/{webdav_account_name}
        在 WSGI 线程中通过 anyio.from_thread.run 调用异步认证逻辑。
        """
        # 解析用户名
        if "/" not in user_name:
            l.debug(f"WebDAV 认证失败: 用户名格式无效 '{user_name}'")
            return False

        email, account_name = user_name.split("/", 1)
        if not email or not account_name:
            l.debug(f"WebDAV 认证失败: 用户名格式无效 '{user_name}'")
            return False

        # 在 WSGI 线程中调用异步认证
        future = asyncio.run_coroutine_threadsafe(
            _authenticate(email, account_name, password),
            EventLoopRef.get(),
        )
        result = future.result()

        if result is None:
            l.debug(f"WebDAV 认证失败: {email}/{account_name}")
            return False

        user_id, webdav_id = result

        # 将认证信息存入 environ，供 Provider 使用
        environ["disknext.user_id"] = user_id
        environ["disknext.webdav_id"] = webdav_id
        environ["disknext.email"] = email
        environ["disknext.account_name"] = account_name

        return True

    def digest_auth_user(
        self,
        realm: str,
        user_name: str,
        environ: dict[str, object],
    ) -> bool:
        """不支持 Digest 认证"""
        return False
