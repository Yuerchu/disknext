"""
AioHttp ClientSession 共享管理模块

提供通过 Mixin 模式管理全局共享的 aiohttp.ClientSession 实例。

设计模式：

- **Mixin + ClassVar**：使用 ClassVar 存储全局单例 ClientSession
- **显式生命周期管理**：通过 initialize_http_session() 和 close_http_session() 管理资源
- **显式状态检查**：在初始化和访问时抛出明确异常，关闭时保持幂等

使用示例::

    from utils.aiohttp_session import AioHttpClientSessionClassVarMixin

    class MyService(AioHttpClientSessionClassVarMixin):
        async def fetch_data(self, url: str) -> dict:
            async with self.http_session.get(url) as resp:
                return await resp.json()

        @classmethod
        async def fetch_static_data(cls, url: str) -> dict:
            async with cls.get_http_session().get(url) as resp:
                return await resp.json()

    # 应用启动时初始化
    await AioHttpClientSessionClassVarMixin.initialize_http_session()

    # 应用关闭时清理
    await AioHttpClientSessionClassVarMixin.close_http_session()
"""
import asyncio
import inspect
import ssl
from collections.abc import AsyncIterator, Awaitable, Callable, Generator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, ClassVar, Protocol, final

import aiohttp
from aiohttp import TraceConfig, TraceRequestStartParams
from aiohttp_socks import ProxyConnector
from loguru import logger as l
from yarl import URL

from .ssrf_resolver import SSRFProtectedResolver

# 模块级配置：日志中 Body 的最大长度，超过则截断。None 表示不截断
_log_body_max_length: int | None = None

# Body 收集硬上限（防止大文件流式上传导致 OOM）
_MAX_BODY_COLLECT_BYTES = 1024 * 1024  # 1MB

_SENSITIVE_HEADERS: frozenset[str] = frozenset({
    'authorization',
    'x-api-key',
    'x-secret-key',
    'cookie',
    'set-cookie',
    'proxy-authorization',
    'x-goog-api-key',
})
"""日志中需要脱敏的敏感 header（全小写匹配）"""


def _sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    """脱敏敏感 header 值，保留前 8 字符用于调试"""
    return {
        k: (f"{v[:8]}***" if len(v) > 8 else "***") if k.lower() in _SENSITIVE_HEADERS else v
        for k, v in headers.items()
    }


async def _on_request_start(
    session: aiohttp.ClientSession,
    trace_config_ctx: aiohttp.tracing.SimpleNamespace,
    params: TraceRequestStartParams,
) -> None:
    """请求开始时记录请求信息"""
    trace_config_ctx.method = params.method
    trace_config_ctx.url = params.url
    trace_config_ctx.headers = _sanitize_headers(dict(params.headers))
    trace_config_ctx.body_chunks: list[bytes] = []
    trace_config_ctx.body_total_size = 0


async def _on_request_chunk_sent(
    session: aiohttp.ClientSession,
    trace_config_ctx: aiohttp.tracing.SimpleNamespace,
    params: aiohttp.TraceRequestChunkSentParams,
) -> None:
    """请求体发送时逐 chunk 收集（上限 _MAX_BODY_COLLECT_BYTES）"""
    trace_config_ctx.body_total_size += len(params.chunk)
    if trace_config_ctx.body_total_size <= _MAX_BODY_COLLECT_BYTES:
        trace_config_ctx.body_chunks.append(params.chunk)


async def _on_request_end(
    session: aiohttp.ClientSession,
    trace_config_ctx: aiohttp.tracing.SimpleNamespace,
    params: aiohttp.TraceRequestEndParams,
) -> None:
    """请求结束时记录完整请求"""
    total_size: int = trace_config_ctx.body_total_size

    if total_size > _MAX_BODY_COLLECT_BYTES:
        body_str = f"(truncated, {total_size} bytes total)"
    elif trace_config_ctx.body_chunks:
        body = b''.join(trace_config_ctx.body_chunks)
        body_str = body.decode('utf-8', errors='replace')
        if _log_body_max_length is not None and len(body_str) > _log_body_max_length:
            half = _log_body_max_length // 2
            body_str = f"{body_str[:half]}...({len(body_str)} chars)...{body_str[-half:]}"
    else:
        body_str = "(empty)"
    # 释放 chunk 引用
    trace_config_ctx.body_chunks.clear()
    l.debug(
        f"[HTTP Request] {trace_config_ctx.method} {trace_config_ctx.url}\n"
        f"Headers: {trace_config_ctx.headers}\n"
        f"Body: {body_str}"
    )


async def _on_request_exception(
    session: aiohttp.ClientSession,
    trace_config_ctx: aiohttp.tracing.SimpleNamespace,
    params: aiohttp.TraceRequestExceptionParams,
) -> None:
    """请求异常时记录详细信息"""
    # 释放 chunk 引用（异常路径也需要清理，防止大文件上传内存泄漏）
    trace_config_ctx.body_chunks.clear()
    l.error(
        f"[HTTP Request Exception] {trace_config_ctx.method} {trace_config_ctx.url}\n"
        f"Exception: {type(params.exception).__name__}: {params.exception}"
    )


def _create_trace_config() -> TraceConfig:
    """创建请求追踪配置"""
    trace_config = TraceConfig()
    trace_config.on_request_start.append(_on_request_start)
    trace_config.on_request_chunk_sent.append(_on_request_chunk_sent)
    trace_config.on_request_end.append(_on_request_end)
    trace_config.on_request_exception.append(_on_request_exception)
    return trace_config


@final
class _RetryableStatusError(Exception):
    """内部异常：HTTP 可重试状态码，用于跳出 async with 块触发重试"""
    __slots__ = ('status', 'body', 'retry_after')

    def __init__(self, status: int, body: str, retry_after: str | None) -> None:
        super().__init__(status, body)
        self.status = status
        self.body = body
        self.retry_after = retry_after


RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})
"""默认触发自动重试的 HTTP 状态码"""


# ==================== Protocol 类型 ====================


class HttpClientContentProtocol(Protocol):
    """共享 HTTP 响应 body 读取协议。"""

    async def read(self, n: int = -1) -> bytes:
        """读取 body 内容。"""
        ...

    def iter_chunked(self, n: int) -> AsyncIterator[bytes]:
        """按块迭代 body。"""
        ...

    def __aiter__(self) -> AsyncIterator[bytes]:
        """逐行或逐块迭代 body。"""
        ...


class HttpClientResponseProtocol(Protocol):
    """共享 HTTP 响应协议。"""

    status: int
    headers: Mapping[str, str]
    content_type: str
    content: HttpClientContentProtocol

    async def read(self) -> bytes:
        """读取完整响应体。"""
        ...

    async def text(self, *args: Any, **kwargs: Any) -> str:
        """读取文本响应体。"""
        ...

    async def json(self, *args: Any, **kwargs: Any) -> Any:
        """解析 JSON 响应体。"""
        ...

    def raise_for_status(self) -> None:
        """状态码错误时抛出异常。"""
        ...

    def release(self) -> None:
        """归还底层连接到连接池（不关闭，复用 keep-alive）。

        非 ``async with`` 形式时，调用方在读完 body 后须显式调用 release()
        以避免连接泄漏。``async with response:`` 退出时会自动 release。
        """
        ...

    async def __aenter__(self) -> 'HttpClientResponseProtocol':
        """进入 async with 上下文。"""
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> bool | None:
        """退出 async with 上下文。"""
        ...


class HttpRequestContextProtocol(Protocol):
    """aiohttp request context manager 的可等待协议。"""

    def __await__(self) -> Generator[Any, None, HttpClientResponseProtocol]:
        """await session.request(...)。"""
        ...

    async def __aenter__(self) -> HttpClientResponseProtocol:
        """async with session.request(...)。"""
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> bool | None:
        """退出 request context。"""
        ...


class HttpClientWebSocketProtocol(Protocol):
    """共享 WebSocket 协议。"""

    async def send_bytes(self, data: bytes) -> None:
        """发送二进制消息。"""
        ...

    async def send_str(self, data: str) -> None:
        """发送文本消息。"""
        ...

    async def send_json(self, data: Any) -> None:
        """发送 JSON 消息。"""
        ...

    async def receive(self) -> aiohttp.WSMessage:
        """接收一条 WebSocket 消息。"""
        ...

    async def close(self) -> None:
        """关闭连接。"""
        ...

    def exception(self) -> BaseException | None:
        """返回底层异常。"""
        ...

    def __aiter__(self) -> AsyncIterator[aiohttp.WSMessage]:
        """异步迭代 WebSocket 消息。"""
        ...


class HttpWebSocketContextProtocol(Protocol):
    """aiohttp ws_connect context manager 的可等待协议。"""

    def __await__(self) -> Generator[Any, None, HttpClientWebSocketProtocol]:
        """await session.ws_connect(...)。"""
        ...

    async def __aenter__(self) -> HttpClientWebSocketProtocol:
        """async with session.ws_connect(...)。"""
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> bool | None:
        """退出 WebSocket context。"""
        ...


class HttpClientSessionProtocol(Protocol):
    """共享 HTTP session 协议。"""

    closed: bool

    def request(self, method: str, url: str | URL, *args: Any, **kwargs: Any) -> HttpRequestContextProtocol:
        """发送任意 HTTP 请求。"""
        ...

    def get(self, url: str | URL, *args: Any, **kwargs: Any) -> HttpRequestContextProtocol:
        """发送 GET 请求。"""
        ...

    def post(self, url: str | URL, *args: Any, **kwargs: Any) -> HttpRequestContextProtocol:
        """发送 POST 请求。"""
        ...

    def put(self, url: str | URL, *args: Any, **kwargs: Any) -> HttpRequestContextProtocol:
        """发送 PUT 请求。"""
        ...

    def delete(self, url: str | URL, *args: Any, **kwargs: Any) -> HttpRequestContextProtocol:
        """发送 DELETE 请求。"""
        ...

    def patch(self, url: str | URL, *args: Any, **kwargs: Any) -> HttpRequestContextProtocol:
        """发送 PATCH 请求。"""
        ...

    def head(self, url: str | URL, *args: Any, **kwargs: Any) -> HttpRequestContextProtocol:
        """发送 HEAD 请求。"""
        ...

    def ws_connect(self, url: str | URL, *args: Any, **kwargs: Any) -> HttpWebSocketContextProtocol:
        """建立 WebSocket 连接。"""
        ...

    async def close(self) -> None:
        """关闭 session。"""
        ...


HttpSessionFactory = Callable[..., Awaitable[HttpClientSessionProtocol] | HttpClientSessionProtocol]
"""共享 HTTP session 工厂，允许测试环境注入自定义实现。"""


# ==================== Mixin ====================


class AioHttpClientSessionClassVarMixin:
    """
    Mixin to provide a shared aiohttp ClientSession for asynchronous HTTP requests.

    The session must be initialized in an async context (e.g., FastAPI startup event)
    by calling ``initialize_http_session()`` before use.

    All classes inheriting this mixin share a single global ClientSession instance.
    """

    # ---- 配置常量（DiskNext 不使用 meta_config，直接硬编码默认值）----
    AIOHTTP_SSL_VERIFY: ClassVar[bool] = True
    AIOHTTP_TIMEOUT_TOTAL: ClassVar[int] = 300
    AIOHTTP_TIMEOUT_CONNECT: ClassVar[int] = 30
    AIOHTTP_TIMEOUT_SOCK_READ: ClassVar[int] = 300
    AIOHTTP_LIMIT: ClassVar[int] = 100
    AIOHTTP_LIMIT_PER_HOST: ClassVar[int] = 30
    AIOHTTP_DNS_NAMESERVERS: ClassVar[str] = "8.8.8.8,1.1.1.1"
    USER_EGRESS_SOCKS5_URL: ClassVar[str | None] = None

    # ---- 全局单例 session ----
    _http_session: ClassVar[HttpClientSessionProtocol | None] = None
    """平台路径 session：系统内部 HTTP 调用走这条"""

    _user_safe_http_session: ClassVar[HttpClientSessionProtocol | None] = None
    """
    用户路径 session：用户提供的外部 URL 调用走这条

    双重防护：
    1. SSRF Resolver 在 DNS 解析阶段阻断所有私网 IP（零 TOCTOU 窗口）
    2. SOCKS5 Connector 透传到独立出口 IP 池（与用户自配 HTTP 代理 Layer 正交）

    初始化策略：
    - ``USER_EGRESS_SOCKS5_URL`` 非空 → 正常模式（SSRF + IP 分流）
    - 为空 → 降级模式（仅 SSRF，无 IP 分流），启动时打印 WARNING 提示运维
    """

    _ssl_context: ClassVar[ssl.SSLContext | None] = None

    @classmethod
    async def initialize_http_session(
        cls,
        ssl_ca_cert_path: Path | None = None,
        disable_strict_verify: bool = False,
        log_body_max_length: int | None = None,
        session_factory: HttpSessionFactory | None = None,
        user_session_factory: HttpSessionFactory | None = None,
        **session_kwargs: Any,
    ) -> None:
        """
        Initialize the aiohttp ClientSession in an async context.

        Should be called during application startup (e.g., FastAPI startup event).

        :param ssl_ca_cert_path: CA 证书路径（可选，用于验证自签名证书）
        :param disable_strict_verify: 禁用 VERIFY_X509_STRICT（解决 Python 3.13+ 间歇性验证失败）
        :param log_body_max_length: 日志中 Body 的最大长度，超过则截断。None 表示不截断
        :param session_factory: 自定义平台 session 工厂（测试用），设置后跳过默认 session 创建
        :param user_session_factory: 自定义用户安全 session 工厂（测试用），设置后跳过 SOCKS5 初始化
        :param session_kwargs: 传递给 aiohttp.ClientSession 的额外参数
        """
        global _log_body_max_length
        if cls._http_session is not None and not cls._http_session.closed:
            raise RuntimeError("HTTP session already initialized")
        _log_body_max_length = log_body_max_length

        # 配置 SSL 上下文
        if not cls.AIOHTTP_SSL_VERIFY:
            l.warning(
                "[HTTP SSL] AIOHTTP_SSL_VERIFY=False: 平台路径 HTTPS 证书验证已禁用。"
                "生产环境请配置正确的 CA 证书链并启用验证。"
            )
            cls._ssl_context = None  # pyright: ignore[reportAttributeAccessIssue]
        elif ssl_ca_cert_path:
            cls._ssl_context = ssl.create_default_context()
            cls._ssl_context.load_verify_locations(ssl_ca_cert_path)
            if disable_strict_verify:
                cls._ssl_context.verify_flags &= ~ssl.VERIFY_X509_STRICT

        if session_factory is not None:
            timeout = aiohttp.ClientTimeout(
                total=cls.AIOHTTP_TIMEOUT_TOTAL,
                connect=cls.AIOHTTP_TIMEOUT_CONNECT,
                sock_read=cls.AIOHTTP_TIMEOUT_SOCK_READ,
            )
            session_kwargs.setdefault('timeout', timeout)
            session_kwargs.setdefault('trust_env', False)
            session_kwargs.setdefault('trace_configs', [_create_trace_config()])
            custom_session = session_factory(**session_kwargs)
            cls._http_session = await custom_session if inspect.isawaitable(custom_session) else custom_session  # pyright: ignore[reportAttributeAccessIssue]
            if user_session_factory is not None:
                user_session = user_session_factory(**session_kwargs)
                cls._user_safe_http_session = await user_session if inspect.isawaitable(user_session) else user_session  # pyright: ignore[reportAttributeAccessIssue]
            return

        # 创建 TCPConnector，配置连接池参数
        resolver = aiohttp.resolver.AsyncResolver(nameservers=cls.AIOHTTP_DNS_NAMESERVERS.split(','))
        # ssl 参数决策
        if not cls.AIOHTTP_SSL_VERIFY:
            ssl_param: ssl.SSLContext | bool = False
        elif cls._ssl_context is not None:
            ssl_param = cls._ssl_context
        else:
            ssl_param = True
        connector = aiohttp.TCPConnector(
            limit=cls.AIOHTTP_LIMIT,
            limit_per_host=cls.AIOHTTP_LIMIT_PER_HOST,
            keepalive_timeout=60,
            force_close=False,
            enable_cleanup_closed=True,
            ttl_dns_cache=300,
            ssl=ssl_param,
            resolver=resolver,
        )
        session_kwargs['connector'] = connector

        # 配置超时
        timeout = aiohttp.ClientTimeout(
            total=cls.AIOHTTP_TIMEOUT_TOTAL,
            connect=cls.AIOHTTP_TIMEOUT_CONNECT,
            sock_read=cls.AIOHTTP_TIMEOUT_SOCK_READ,
        )
        session_kwargs.setdefault('timeout', timeout)

        cls._http_session = aiohttp.ClientSession(  # pyright: ignore[reportAttributeAccessIssue]
            trust_env=False,
            trace_configs=[_create_trace_config()],
            **session_kwargs,
        )

        # ---- 用户路径 session（SSRF 保护 + 可选 SOCKS5）----
        user_timeout = aiohttp.ClientTimeout(
            total=cls.AIOHTTP_TIMEOUT_TOTAL,
            connect=cls.AIOHTTP_TIMEOUT_CONNECT,
            sock_read=cls.AIOHTTP_TIMEOUT_SOCK_READ,
        )
        ssrf_resolver = SSRFProtectedResolver(
            nameservers=cls.AIOHTTP_DNS_NAMESERVERS.split(','),
        )

        if cls.USER_EGRESS_SOCKS5_URL:
            # 正常模式：SOCKS5 到 egress pod + SSRF resolver 双保险
            user_connector = ProxyConnector.from_url(
                cls.USER_EGRESS_SOCKS5_URL,
                resolver=ssrf_resolver,
                limit=cls.AIOHTTP_LIMIT,
                limit_per_host=cls.AIOHTTP_LIMIT_PER_HOST,
                keepalive_timeout=60,
                force_close=False,
                enable_cleanup_closed=True,
                ttl_dns_cache=300,
                ssl=cls._ssl_context if cls._ssl_context is not None else True,
            )
            l.info(
                f"[user-safe HTTP] 正常模式: SOCKS5 egress = "
                f"{cls.USER_EGRESS_SOCKS5_URL}; SSRFProtectedResolver 已启用"
            )
        else:
            # 降级模式：无 SOCKS5，仅 SSRF resolver 保护
            l.warning(
                "[user-safe HTTP] 降级模式: USER_EGRESS_SOCKS5_URL 未配置。"
                "用户路径仅有 SSRFProtectedResolver 保护，无独立出口 IP 分流。"
            )
            user_connector = aiohttp.TCPConnector(
                resolver=ssrf_resolver,
                limit=cls.AIOHTTP_LIMIT,
                limit_per_host=cls.AIOHTTP_LIMIT_PER_HOST,
                keepalive_timeout=60,
                force_close=False,
                enable_cleanup_closed=True,
                ttl_dns_cache=300,
                ssl=cls._ssl_context if cls._ssl_context is not None else True,
            )

        cls._user_safe_http_session = aiohttp.ClientSession(  # pyright: ignore[reportAttributeAccessIssue]
            connector=user_connector,
            timeout=user_timeout,
            trust_env=False,
            trace_configs=[_create_trace_config()],
        )

    @classmethod
    def get_http_session(cls) -> HttpClientSessionProtocol:
        """
        Get the aiohttp ClientSession instance at class level.

        :return: An instance of aiohttp.ClientSession.
        """
        session = cls._http_session
        if session is None or session.closed:
            raise RuntimeError(
                "HTTP session not initialized. "
                "Call `AioHttpClientSessionClassVarMixin.initialize_http_session()` "
                "during application startup (e.g., in FastAPI startup event)."
            )
        return session

    @classmethod
    def get_user_safe_http_session(cls) -> HttpClientSessionProtocol:
        """
        Get the user-safe aiohttp ClientSession instance at class level.

        用户提供的外部 URL 应使用此 session，内置 SSRF 防护 + 可选 SOCKS5 egress。

        :return: aiohttp.ClientSession 实例（用户路径）
        """
        session = cls._user_safe_http_session
        if session is None or session.closed:
            raise RuntimeError(
                "User-safe HTTP session not initialized. "
                "Call `AioHttpClientSessionClassVarMixin.initialize_http_session()` "
                "during application startup."
            )
        return session

    @classmethod
    def get_ssl_context(cls) -> ssl.SSLContext | None:
        """获取 SSL 上下文"""
        return cls._ssl_context

    @property
    def http_session(self) -> HttpClientSessionProtocol:
        """
        Get the aiohttp ClientSession instance.

        Delegates to the class-level get_http_session() method.

        :return: An instance of aiohttp.ClientSession.
        """
        return self.__class__.get_http_session()

    def _pick_http_session(self) -> HttpClientSessionProtocol:
        """
        选择本次 HTTP 调用使用的 session（模板方法）

        默认返回平台 session。子类可覆盖此方法实现自定义分流逻辑，
        例如根据来源将用户提供的 URL 路由到 ``_user_safe_http_session``。
        """
        return self.__class__.get_http_session()

    @classmethod
    async def close_http_session(cls) -> None:
        """
        Close the aiohttp ClientSession(s) if open.

        同时关闭平台 session 和用户 session，两者都是应用级单例。

        Should be called during application shutdown (e.g., FastAPI shutdown event).
        """
        # 平台 session
        session = cls._http_session
        if session is not None and not session.closed:
            await session.close()
        cls._http_session = None  # pyright: ignore[reportAttributeAccessIssue]

        # 用户 session
        user_session = cls._user_safe_http_session
        if user_session is not None and not user_session.closed:
            await user_session.close()
        cls._user_safe_http_session = None  # pyright: ignore[reportAttributeAccessIssue]

    @asynccontextmanager
    async def _http_request_with_retry(
        self,
        method: str,
        url: str,
        *,
        max_retries: int = 5,
        retry_base_delay: float = 1.0,
        retry_max_delay: float = 30.0,
        retryable_statuses: frozenset[int] = RETRYABLE_STATUS_CODES,
        should_retry: Callable[[int, str], bool] | None = None,
        **request_kwargs: Any,
    ) -> AsyncIterator[HttpClientResponseProtocol]:
        """
        带自动重试的 HTTP 请求上下文管理器。

        对瞬时网络故障（连接错误、超时）和可重试的 HTTP 状态码（429/5xx）
        自动重试，使用指数退避策略。支持 Retry-After 响应头。

        用法::

            async with self._http_request_with_retry('POST', url, json=data) as resp:
                if resp.status != 200:
                    raise SomeError(await resp.text())
                data = await resp.json()

        :param method: HTTP 方法（GET, POST 等）
        :param url: 请求 URL
        :param max_retries: 最大重试次数（不含首次请求，默认 5 次）
        :param retry_base_delay: 首次重试的基础延迟秒数
        :param retry_max_delay: 重试延迟上限秒数
        :param retryable_statuses: 触发重试的 HTTP 状态码集合
        :param should_retry: 自定义重试判断回调 (status, body) -> bool，
            用于状态码不在 retryable_statuses 中但需要根据响应内容判断是否重试的场景。
            仅在非 2xx 响应时调用。
        :param request_kwargs: 传递给 aiohttp 的请求参数（headers, json, proxy, timeout 等）
        """
        delay = retry_base_delay

        for attempt in range(max_retries + 1):
            is_last_attempt = attempt == max_retries
            yielded = False
            try:
                async with self._pick_http_session().request(method, url, **request_kwargs) as response:
                    if not is_last_attempt and not (200 <= response.status < 300):
                        # 标准可重试状态码
                        if response.status in retryable_statuses:
                            error_body = await response.text()
                            retry_after = response.headers.get('Retry-After')
                            raise _RetryableStatusError(response.status, error_body, retry_after)
                        # 自定义重试判断（仅非 2xx 才读取 body 检查）
                        if should_retry is not None:
                            error_body = await response.text()
                            if should_retry(response.status, error_body):
                                raise _RetryableStatusError(
                                    response.status, error_body, response.headers.get('Retry-After'),
                                )
                    yielded = True
                    yield response
                    return

            except _RetryableStatusError as e:
                actual_delay = delay
                if e.retry_after is not None:
                    try:
                        actual_delay = max(float(e.retry_after), delay)
                    except ValueError:
                        pass
                l.warning(
                    f"[HTTP Retry] {method} {url} 返回 {e.status} "
                    f"(重试 {attempt + 1}/{max_retries}, 等待 {actual_delay:.1f}s): "
                    f"{e.body[:200]}"
                )
                await asyncio.sleep(actual_delay)
                delay = min(delay * 2, retry_max_delay)

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if yielded:
                    raise  # 响应已开始消费，中途错误不重试
                if not is_last_attempt:
                    l.warning(
                        f"[HTTP Retry] {method} {url} 失败 "
                        f"(重试 {attempt + 1}/{max_retries}, 等待 {delay:.1f}s): "
                        f"{type(e).__name__}: {e}"
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, retry_max_delay)
                else:
                    raise
