from pathlib import Path
from typing import NoReturn

from fastapi import FastAPI, Request
from loguru import logger as l

from routers import router
from routers.dav import dav_app
from routers.dav.provider import EventLoopRef
from utils.redis import RedisManager
from utils.storage import S3StorageDriver
from sqlmodels.database_connection import DatabaseManager
from sqlmodels.migration import migration
from utils.conf import appmeta
from utils.http.http_exceptions import raise_internal_error
from utils.lifespan import lifespan

STATICS_DIR: Path = (Path(__file__).parent / "statics").resolve()
"""前端静态文件目录（由 Docker 构建时复制）"""

async def _init_db() -> None:
    """初始化数据库连接引擎"""
    await DatabaseManager.init(appmeta.database_url, debug=appmeta.debug)

# 捕获事件循环引用（供 WSGI 线程桥接使用）
lifespan.add_startup(EventLoopRef.capture)

# 添加初始化数据库启动项
lifespan.add_startup(_init_db)
lifespan.add_startup(migration)
lifespan.add_startup(RedisManager.connect)
lifespan.add_startup(S3StorageDriver.initialize_session)

# 添加关闭项
lifespan.add_shutdown(S3StorageDriver.close_session)
lifespan.add_shutdown(DatabaseManager.close)
lifespan.add_shutdown(RedisManager.disconnect)

# 创建应用实例并设置元数据
app = FastAPI(
    title=appmeta.APP_NAME,
    summary=appmeta.summary,
    description=appmeta.description,
    version=appmeta.BackendVersion,
    license_info=appmeta.license_info,
    lifespan=lifespan.lifespan,
    debug=appmeta.debug,
    openapi_url="/openapi.json" if appmeta.debug else None,
)
# 添加跨域 CORS 中间件,仅在调试模式下启用,以允许所有来源访问 API
if appmeta.debug:
    from fastapi.middleware.cors import CORSMiddleware
    from sqlmodel_ext import RelationLoadCheckMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RelationLoadCheckMiddleware)

@app.exception_handler(Exception)
async def handle_unexpected_exceptions(
    request: Request,
    exc: Exception
) -> NoReturn:
    """
    捕获所有未经处理的 FastAPI 异常,防止敏感信息泄露。
    """
    l.exception(exc)
    l.error(f"An unhandled exception occurred for request: {request.method} {request.url.path}")

    raise_internal_error()

# 挂载路由
app.include_router(router)

# 挂载 WebDAV 协议端点（优先于 SPA catch-all）
app.mount("/dav", dav_app)

# 防止直接运行 main.py
if __name__ == "__main__":
    l.error("请用 fastapi ['dev', 'run'] 命令启动服务")
    exit(1)
