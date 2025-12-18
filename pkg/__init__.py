# 延迟导入以避免循环依赖
# JWT 和 lifespan 应在需要时直接从子模块导入
# from .JWT import JWT
# from .lifespan import lifespan