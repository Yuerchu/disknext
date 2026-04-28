from fastapi import APIRouter, Depends

from middleware.scope import require_scope
from sqlmodels import ResponseBase
from utils import http_exceptions

download_router = APIRouter(
    prefix="/download",
    tags=["下载 download"]
)

aria2_router = APIRouter(
    prefix="/aria2",
    tags=["下载 aria2"]
)

download_router.include_router(aria2_router)

@aria2_router.post(
    path='/url',
    summary='创建URL下载任务',
    description='Create a URL download task endpoint.',
    dependencies=[Depends(require_scope("aria2:create:own"))]
)
def router_aria2_url() -> ResponseBase:
    """
    Create a URL download task endpoint.
    
    Returns:
        ResponseBase: A model containing the response data for the URL download task.
    """
    http_exceptions.raise_not_implemented()

@aria2_router.post(
    path='/torrent/{id}',
    summary='创建种子下载任务',
    description='Create a torrent download task endpoint.',
    dependencies=[Depends(require_scope("aria2:create:own"))]
)
def router_aria2_torrent(id: str) -> ResponseBase:
    """
    Create a torrent download task endpoint.
    
    Args:
        id (str): The ID of the torrent to download.
    
    Returns:
        ResponseBase: A model containing the response data for the torrent download task.
    """
    http_exceptions.raise_not_implemented()

@aria2_router.put(
    path='/select/{gid}',
    summary='重新选择要下载的文件',
    description='Re-select files to download endpoint.',
    dependencies=[Depends(require_scope("aria2:write:own"))]
)
def router_aria2_select(gid: str) -> ResponseBase:
    """
    Re-select files to download endpoint.
    
    Args:
        gid (str): The GID of the download task.
    
    Returns:
        ResponseBase: A model containing the response data for the re-selection of files.
    """
    http_exceptions.raise_not_implemented()

@aria2_router.delete(
    path='/task/{gid}',
    summary='取消或删除下载任务',
    description='Delete a download task endpoint.',
    dependencies=[Depends(require_scope("aria2:delete:own"))]
)
def router_aria2_delete(gid: str) -> ResponseBase:
    """
    Delete a download task endpoint.
    
    Args:
        gid (str): The GID of the download task to delete.
    
    Returns:
        ResponseBase: A model containing the response data for the deletion of the download task.
    """
    http_exceptions.raise_not_implemented()

@aria2_router.get(
    '/downloading',
    summary='获取正在下载中的任务',
    description='Get currently downloading tasks endpoint.',
    dependencies=[Depends(require_scope("aria2:read:own"))]
)
def router_aria2_downloading() -> ResponseBase:
    """
    Get currently downloading tasks endpoint.
    
    Returns:
        ResponseBase: A model containing the response data for currently downloading tasks.
    """
    http_exceptions.raise_not_implemented()

@aria2_router.get(
    path='/finished',
    summary='获取已完成的任务',
    description='Get finished tasks endpoint.',
    dependencies=[Depends(require_scope("aria2:read:own"))]
)
def router_aria2_finished() -> ResponseBase:
    """
    Get finished tasks endpoint.
    
    Returns:
        ResponseBase: A model containing the response data for finished tasks.
    """
    http_exceptions.raise_not_implemented()