from fastapi import APIRouter, Depends
from middleware.auth import auth_required

from models import ResponseBase
from utils import http_exceptions

tag_router = APIRouter(
    prefix='/tag',
    tags=["tag"],
)

@tag_router.post(
    path='/filter',
    summary='创建文件分类标签',
    description='Create a file classification tag.',
    dependencies=[Depends(auth_required)],
)
def router_tag_create_filter() -> ResponseBase:
    """
    Create a file classification tag.
    
    Returns:
        ResponseBase: A model containing the response data for the created tag.
    """
    http_exceptions.raise_not_implemented()

@tag_router.post(
    path='/link',
    summary='创建目录快捷方式标签',
    description='Create a directory shortcut tag.',
    dependencies=[Depends(auth_required)],
)
def router_tag_create_link() -> ResponseBase:
    """
    Create a directory shortcut tag.
    
    Returns:
        ResponseBase: A model containing the response data for the created tag.
    """
    http_exceptions.raise_not_implemented()

@tag_router.delete(
    path='/{id}',
    summary='删除标签',
    description='Delete a tag by its ID.',
    dependencies=[Depends(auth_required)],
)
def router_tag_delete(id: str) -> ResponseBase:
    """
    Delete a tag by its ID.
    
    Args:
        id (str): The ID of the tag to be deleted.
    
    Returns:
        ResponseBase: A model containing the response data for the deletion operation.
    """
    http_exceptions.raise_not_implemented()