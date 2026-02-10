from fastapi import APIRouter, Depends

from middleware.auth import auth_required
from sqlmodels import ResponseBase
from utils import http_exceptions

# WebDAV 管理路由
webdav_router = APIRouter(
    prefix='/webdav',
    tags=["webdav"],
)

@webdav_router.get(
    path='/accounts',
    summary='获取账号信息',
    description='Get account information for WebDAV.',
    dependencies=[Depends(auth_required)],
)
def router_webdav_accounts() -> ResponseBase:
    """
    Get account information for WebDAV.
    
    Returns:
        ResponseBase: A model containing the response data for the account information.
    """
    http_exceptions.raise_not_implemented()

@webdav_router.post(
    path='/accounts',
    summary='新建账号',
    description='Create a new WebDAV account.',
    dependencies=[Depends(auth_required)],
)
def router_webdav_create_account() -> ResponseBase:
    """
    Create a new WebDAV account.
    
    Returns:
        ResponseBase: A model containing the response data for the created account.
    """
    http_exceptions.raise_not_implemented()

@webdav_router.delete(
    path='/accounts/{id}',
    summary='删除账号',
    description='Delete a WebDAV account by its ID.',
    dependencies=[Depends(auth_required)],
)
def router_webdav_delete_account(id: str) -> ResponseBase:
    """
    Delete a WebDAV account by its ID.
    
    Args:
        id (str): The ID of the account to be deleted.
    
    Returns:
        ResponseBase: A model containing the response data for the deletion operation.
    """
    http_exceptions.raise_not_implemented()

@webdav_router.post(
    path='/mount',
    summary='新建目录挂载',
    description='Create a new WebDAV mount point.',
    dependencies=[Depends(auth_required)],
)
def router_webdav_create_mount() -> ResponseBase:
    """
    Create a new WebDAV mount point.
    
    Returns:
        ResponseBase: A model containing the response data for the created mount point.
    """
    http_exceptions.raise_not_implemented()

@webdav_router.delete(
    path='/mount/{id}',
    summary='删除目录挂载',
    description='Delete a WebDAV mount point by its ID.',
    dependencies=[Depends(auth_required)],
)
def router_webdav_delete_mount(id: str) -> ResponseBase:
    """
    Delete a WebDAV mount point by its ID.
    
    Args:
        id (str): The ID of the mount point to be deleted.
    
    Returns:
        ResponseBase: A model containing the response data for the deletion operation.
    """
    http_exceptions.raise_not_implemented()

@webdav_router.patch(
    path='accounts/{id}',
    summary='更新账号信息',
    description='Update WebDAV account information by ID.',
    dependencies=[Depends(auth_required)],
)
def router_webdav_update_account(id: str) -> ResponseBase:
    """
    Update WebDAV account information by ID.
    
    Args:
        id (str): The ID of the account to be updated.
    
    Returns:
        ResponseBase: A model containing the response data for the updated account.
    """
    http_exceptions.raise_not_implemented()