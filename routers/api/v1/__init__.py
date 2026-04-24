from fastapi import APIRouter

from utils.conf import appmeta

from .admin import admin_router

from .callback import callback_router
from .category import category_router
from .directory import directory_router
from .download import download_router
from .file import router as file_router
from .entry import entry_router
from .share import share_router
from .trash import trash_router
from .site import site_router
from .slave import slave_router
from .user import user_router
from .webdav import webdav_router

router = APIRouter(prefix="/v1")

# [TODO] 如果是主机，导入下面的路由

if appmeta.mode == "master":
    router.include_router(admin_router)
    router.include_router(callback_router)
    router.include_router(category_router)
    router.include_router(directory_router)
    router.include_router(download_router)
    router.include_router(file_router)
    router.include_router(entry_router)
    router.include_router(share_router)
    router.include_router(site_router)
    router.include_router(trash_router)
    router.include_router(user_router)
    router.include_router(webdav_router)
elif appmeta.mode == "slave":
    router.include_router(slave_router)
else:
    raise ValueError("Config `mode` must in ['master', 'slave']")