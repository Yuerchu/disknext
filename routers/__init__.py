from fastapi import APIRouter

from .api import router as api_router
from .wopi import wopi_router

router = APIRouter()
router.include_router(api_router)
router.include_router(wopi_router)