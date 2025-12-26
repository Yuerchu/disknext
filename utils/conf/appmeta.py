import os

from dotenv import load_dotenv
from loguru import logger as log

load_dotenv()

APP_NAME = 'DiskNext Server'
summary = '一款基于 FastAPI 的可公私兼备的网盘系统'
description = 'DiskNext Server 是一款基于 FastAPI 的网盘系统，支持个人和企业使用。它提供了高性能的文件存储和管理功能，支持多种认证方式。'
license_info = {"name": "GPLv3", "url": "https://opensource.org/license/gpl-3.0"}

BackendVersion = "0.0.1"

IsPro = False

mode: str = os.getenv('MODE', 'master')

debug: bool = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes") or False

if debug:
    log.warning("Debug mode is enabled. This is not recommended for production use.")

database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///disknext.db")