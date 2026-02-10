from typing import AsyncGenerator, ClassVar

from loguru import logger
from sqlalchemy import NullPool, AsyncAdaptedQueuePool
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession


class DatabaseManager:
    engine: ClassVar[AsyncEngine | None] = None
    _async_session_factory: ClassVar[sessionmaker | None] = None

    @classmethod
    async def get_session(cls) -> AsyncGenerator[AsyncSession]:
        assert cls._async_session_factory is not None, "数据库引擎未初始化，请先调用 DatabaseManager.init()"
        async with cls._async_session_factory() as session:
            yield session

    @classmethod
    async def init(
            cls,
            database_url: str,
            debug: bool = False,
    ):
        """
        初始化数据库连接引擎。

        :param database_url: 数据库连接URL
        :param debug: 是否开启调试模式
        """
        # 构建引擎参数
        engine_kwargs: dict = {
            'echo': debug,
            'future': True,
        }

        if debug:
            # Debug 模式使用 NullPool（无连接池，每次创建新连接）
            engine_kwargs['poolclass'] = NullPool
        else:
            # 生产模式使用 AsyncAdaptedQueuePool 连接池
            engine_kwargs.update({
                'poolclass': AsyncAdaptedQueuePool,
                'pool_size': 40,
                'max_overflow': 80,
                'pool_timeout': 30,
                'pool_recycle': 1800,
                'pool_pre_ping': True,
            })

        # 只在需要时添加 connect_args
        if database_url.startswith("sqlite"):
            engine_kwargs['connect_args'] = {'check_same_thread': False}

        cls.engine = create_async_engine(database_url, **engine_kwargs)

        cls._async_session_factory = sessionmaker(cls.engine, class_=AsyncSession)

        # 开发阶段直接 create_all 创建表结构
        async with cls.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

        logger.info("数据库引擎初始化完成")

    @classmethod
    async def close(cls):
        """
        优雅地关闭数据库连接引擎。
        仅应在应用结束时调用。
        """
        if cls.engine:
            logger.info("正在关闭数据库连接引擎...")
            await cls.engine.dispose()
            logger.info("数据库连接引擎已成功关闭。")
        else:
            logger.info("数据库连接引擎未初始化，无需关闭。")
