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

mode: str = os.getenv('MODE', 'master')
"""运行模式"""

debug: bool = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes") or False
"""是否启用调试模式"""

if debug:
    log.warning("Debug mode is enabled. This is not recommended for production use.")

_database_url = os.getenv("DATABASE_URL")
if not _database_url:
    raise RuntimeError(
        "必须设置 DATABASE_URL 环境变量，DiskNext 只支持 PostgreSQL（asyncpg 驱动）。"
        "示例：postgresql+asyncpg://user:pass@host:5432/dbname"
    )
if not _database_url.startswith("postgresql"):
    raise RuntimeError(
        f"DiskNext 只支持 PostgreSQL，当前 DATABASE_URL 前缀无效: {_database_url.split('://', 1)[0]}"
    )
database_url: str = _database_url
"""PostgreSQL 数据库连接 URL（必需，格式：postgresql+asyncpg://...）"""

_redis_url = os.getenv("REDIS_URL")
if not _redis_url:
    raise RuntimeError(
        "必须设置 REDIS_URL 环境变量，DiskNext 强制要求 Redis。"
        "示例：redis://:password@host:6379/0"
    )
redis_url: str = _redis_url
"""Redis 连接 URL（必需，完整格式：redis://[:password@]host:port/db）"""
