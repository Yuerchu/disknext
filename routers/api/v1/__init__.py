from fastapi import APIRouter

from .admin import admin_router
from .admin import admin_aria2_router
from .admin import admin_file_router
from .admin import admin_group_router
from .admin import admin_policy_router
from .admin import admin_share_router
from .admin import admin_task_router
from .admin import admin_user_router
from .admin import admin_vas_router

from .callback import callback_router
from .directory import directory_router
from .download import download_router
from .file import router as file_router
from .object import object_router
from .share import share_router
from .site import site_router
from .slave import slave_router
from .user import user_router
from .vas import vas_router
from .webdav import webdav_router

router = APIRouter(prefix="/v1")

router.include_router(admin_router)
router.include_router(admin_aria2_router)
router.include_router(admin_file_router)
router.include_router(admin_group_router)
router.include_router(admin_policy_router)
router.include_router(admin_share_router)
router.include_router(admin_task_router)
router.include_router(admin_user_router)
router.include_router(admin_vas_router)

router.include_router(callback_router)
router.include_router(directory_router)
router.include_router(download_router)
router.include_router(file_router)
router.include_router(object_router)
router.include_router(share_router)
router.include_router(site_router)
router.include_router(slave_router)
router.include_router(user_router)
router.include_router(vas_router)
router.include_router(webdav_router)
