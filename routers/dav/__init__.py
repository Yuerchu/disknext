"""
WebDAV 协议入口

使用 WsgiDAV + a2wsgi 提供 WebDAV 协议支持。
WsgiDAV 在 a2wsgi 的线程池中运行，不阻塞 FastAPI 事件循环。

[TODO] 后续此模块将拆分到单独的容器中
"""
from starlette.middleware.wsgi import WSGIMiddleware
from wsgidav.wsgidav_app import WsgiDAVApp

from .domain_controller import DiskNextDomainController
from .provider import DiskNextDAVProvider

_wsgidav_config: dict[str, object] = {
    "provider_mapping": {
        "/": DiskNextDAVProvider(),
    },
    "http_authenticator": {
        "domain_controller": DiskNextDomainController,
        "accept_basic": True,
        "accept_digest": False,
        "default_to_digest": False,
    },
    "verbose": 1,
    # 使用 WsgiDAV 内置的内存锁管理器
    "lock_storage": True,
    # 禁用 WsgiDAV 的目录浏览器（纯 DAV 协议）
    "dir_browser": {
        "enable": False,
    },
}

_wsgidav_app = WsgiDAVApp(_wsgidav_config)

dav_app = WSGIMiddleware(_wsgidav_app)
"""ASGI 应用，挂载到 /dav 路径"""
