import os

from dotenv import load_dotenv
from loguru import logger as log

load_dotenv()

APP_NAME = 'DiskNext Server'
summary = '一款基于 FastAPI 的可公私兼备的网盘系统'
description = 'DiskNext Server 是一款基于 FastAPI 的网盘系统，支持个人和企业使用。它提供了高性能的文件存储和管理功能，支持多种认证方式。'
license_info = {"name": "GPLv3", "url": "https://opensource.org/license/gpl-3.0"}

BackendVersion = "0.0.1"
"""后端版本"""

IsPro = False

mode: str = os.getenv('MODE', 'master')
"""运行模式"""

debug: bool = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes") or False
"""是否启用调试模式"""

if debug:
    log.warning("Debug mode is enabled. This is not recommended for production use.")

database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///disknext.db")
"""数据库地址"""

redis_url: str | None = os.getenv("REDIS_URL")
"""Redis 主机地址"""

_redis_port = os.getenv("REDIS_PORT")
redis_port: int = int(_redis_port) if _redis_port else 6379
"""Redis 端口，默认 6379"""

redis_password: str | None = os.getenv("REDIS_PASSWORD")
"""Redis 密码"""

_redis_db = os.getenv("REDIS_DB")
redis_db: int = int(_redis_db) if _redis_db else 0
"""Redis 数据库索引，默认 0"""

_redis_protocol = os.getenv("REDIS_PROTOCOL")
redis_protocol: int = int(_redis_protocol) if _redis_protocol else 3
"""Redis 协议版本，默认 3"""