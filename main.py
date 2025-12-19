from fastapi import FastAPI

from utils.conf import appmeta
from utils.lifespan import lifespan
from models.database import init_db
from models.migration import migration
from utils.JWT import JWT
from routers import routers

# 添加初始化数据库启动项
lifespan.add_startup(init_db)
lifespan.add_startup(migration)
lifespan.add_startup(JWT.load_secret_key)

# 创建应用实例并设置元数据
app = FastAPI(
    title=appmeta.APP_NAME,
    summary=appmeta.summary,
    description=appmeta.description,
    version=appmeta.BackendVersion,
    openapi_tags=appmeta.tags_meta,
    license_info=appmeta.license_info,
    lifespan=lifespan.lifespan,
    debug=appmeta.debug,
)

# 挂载路由
for router in routers.Router:
    app.include_router(router, prefix='/api')

# 启动时打印欢迎信息
if __name__ == "__main__":
    import uvicorn

    if appmeta.debug:
        uvicorn.run(app='main:app', reload=True)
    else:
        uvicorn.run(app=app)