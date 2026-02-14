"""
WOPI（Web Application Open Platform Interface）路由

挂载在根级别 /wopi（非 /api/v1 下），因为 WOPI 客户端要求标准路径。
"""
from fastapi import APIRouter

from .files import wopi_files_router

wopi_router = APIRouter(prefix="/wopi", tags=["wopi"])
wopi_router.include_router(wopi_files_router)
