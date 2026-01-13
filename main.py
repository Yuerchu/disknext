from typing import NoReturn

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from utils.conf import appmeta
from utils.http.http_exceptions import raise_internal_error
from utils.lifespan import lifespan
from models.database import init_db
from models.migration import migration
from utils import JWT
from routers import router
from service.redis import RedisManager
from loguru import logger as l

# 添加初始化数据库启动项
lifespan.add_startup(init_db)
lifespan.add_startup(migration)
lifespan.add_startup(JWT.load_secret_key)
lifespan.add_startup(RedisManager.connect)

# 添加关闭项
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

# 配置 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发环境允许所有来源，生产环境应该限制为具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
=======
# 添加跨域 CORS 中间件,仅在调试模式下启用,以允许所有来源访问 API
if appmeta.debug:
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
>>>>>>> d2c914cff89e566b0b7ab7a2655ae72905f888f5

@app.exception_handler(Exception)
async def handle_unexpected_exceptions(request: Request, exc: Exception) -> NoReturn:
    """
    捕获所有未经处理的 FastAPI 异常,防止敏感信息泄露。
    """
    l.exception(exc)
    l.error(f"An unhandled exception occurred for request: {request.method} {request.url.path}")

    raise_internal_error()

# 挂载路由
app.include_router(router)

# 防止直接运行 main.py
if __name__ == "__main__":
    l.error("请用 fastapi ['dev', 'run'] 命令启动服务")
    exit(1)
    