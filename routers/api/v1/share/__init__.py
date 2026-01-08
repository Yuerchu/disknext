from typing import Annotated, Literal
from uuid import uuid4
from datetime import datetime

from fastapi import APIRouter, Depends, Query, HTTPException
from loguru import logger as l

from middleware.auth import auth_required
from middleware.dependencies import SessionDep
from models import ResponseBase
from models.user import User
from models.share import Share, ShareCreateRequest, ShareResponse
from models.object import Object
from models.mixin import ListResponse, TableViewRequest
from utils import http_exceptions
from utils.password.pwd import Password

share_router = APIRouter(
    prefix='/share',
    tags=["share"],
)

@share_router.get(
    path='/{id}',
    summary='获取分享',
    description='Get shared content by info type and ID.',
)
def router_share_get(info: str, id: str) -> ResponseBase:
    """
    Get shared content by info type and ID.
    
    Args:
        info (str): The type of information being shared.
        id (str): The ID of the shared content.
    
    Returns:
        dict: A dictionary containing shared content information.
    """
    http_exceptions.raise_not_implemented()

@share_router.put(
    path='/download/{id}',
    summary='创建文件下载会话',
    description='Create a file download session by ID.',
)
def router_share_download(id: str) -> ResponseBase:
    """
    Create a file download session by ID.
    
    Args:
        id (str): The ID of the file to be downloaded.
    
    Returns:
        dict: A dictionary containing download session information.
    """
    http_exceptions.raise_not_implemented()

@share_router.get(
    path='preview/{id}',
    summary='预览分享文件',
    description='Preview shared file by ID.',
)
def router_share_preview(id: str) -> ResponseBase:
    """
    Preview shared file by ID.
    
    Args:
        id (str): The ID of the file to be previewed.
    
    Returns:
        dict: A dictionary containing preview information.
    """
    http_exceptions.raise_not_implemented()

@share_router.get(
    path='/doc/{id}',
    summary='取得Office文档预览地址',
    description='Get Office document preview URL by ID.',
)
def router_share_doc(id: str) -> ResponseBase:
    """
    Get Office document preview URL by ID.
    
    Args:
        id (str): The ID of the Office document.
    
    Returns:
        dict: A dictionary containing the document preview URL.
    """
    http_exceptions.raise_not_implemented()

@share_router.get(
    path='/content/{id}',
    summary='获取文本文件内容',
    description='Get text file content by ID.',
)
def router_share_content(id: str) -> ResponseBase:
    """
    Get text file content by ID.
    
    Args:
        id (str): The ID of the text file.
    
    Returns:
        str: The content of the text file.
    """
    http_exceptions.raise_not_implemented()

@share_router.get(
    path='/list/{id}/{path:path}',
    summary='获取目录列文件',
    description='Get directory listing by ID and path.',
)
def router_share_list(id: str, path: str = '') -> ResponseBase:
    """
    Get directory listing by ID and path.
    
    Args:
        id (str): The ID of the directory.
        path (str): The path within the directory.
    
    Returns:
        dict: A dictionary containing directory listing information.
    """
    http_exceptions.raise_not_implemented()

@share_router.get(
    path='/search/{id}/{type}/{keywords}',
    summary='分享目录搜索',
    description='Search within a shared directory by ID, type, and keywords.',
)
def router_share_search(id: str, type: str, keywords: str) -> ResponseBase:
    """
    Search within a shared directory by ID, type, and keywords.
    
    Args:
        id (str): The ID of the shared directory.
        type (str): The type of search (e.g., file, folder).
        keywords (str): The keywords to search for.
    
    Returns:
        dict: A dictionary containing search results.
    """
    http_exceptions.raise_not_implemented()

@share_router.post(
    path='/archive/{id}',
    summary='归档打包下载',
    description='Archive and download shared content by ID.',
)
def router_share_archive(id: str) -> ResponseBase:
    """
    Archive and download shared content by ID.
    
    Args:
        id (str): The ID of the content to be archived.
    
    Returns:
        dict: A dictionary containing archive download information.
    """
    http_exceptions.raise_not_implemented()

@share_router.get(
    path='/readme/{id}',
    summary='获取README文本文件内容',
    description='Get README text file content by ID.',
)
def router_share_readme(id: str) -> ResponseBase:
    """
    Get README text file content by ID.
    
    Args:
        id (str): The ID of the README file.
    
    Returns:
        str: The content of the README file.
    """
    http_exceptions.raise_not_implemented()

@share_router.get(
    path='/thumb/{id}/{file}',
    summary='获取缩略图',
    description='Get thumbnail image by ID and file name.',
)
def router_share_thumb(id: str, file: str) -> ResponseBase:
    """
    Get thumbnail image by ID and file name.
    
    Args:
        id (str): The ID of the shared content.
        file (str): The name of the file for which to get the thumbnail.
    
    Returns:
        str: A Base64 encoded string of the thumbnail image.
    """
    http_exceptions.raise_not_implemented()

@share_router.post(
    path='/report/{id}',
    summary='举报分享',
    description='Report shared content by ID.',
)
def router_share_report(id: str) -> ResponseBase:
    """
    Report shared content by ID.
    
    Args:
        id (str): The ID of the shared content to report.
    
    Returns:
        dict: A dictionary containing report submission information.
    """
    http_exceptions.raise_not_implemented()

@share_router.get(
    path='/search',
    summary='搜索公共分享',
    description='Search public shares by keywords and type.',
)
def router_share_search_public(keywords: str, type: str = 'all') -> ResponseBase:
    """
    Search public shares by keywords and type.
    
    Args:
        keywords (str): The keywords to search for.
        type (str): The type of search (e.g., all, file, folder).
    
    Returns:
        dict: A dictionary containing search results for public shares.
    """
    http_exceptions.raise_not_implemented()

#####################
# 需要登录的接口
#####################

@share_router.post(
    path='/',
    summary='创建新分享',
    description='Create a new share endpoint.',
)
async def router_share_create(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    request: ShareCreateRequest,
) -> ShareResponse:
    """
    创建新分享

    认证：需要 JWT token

    流程：
    1. 验证对象存在且属于当前用户
    2. 生成随机分享码（uuid4）
    3. 如果有密码则加密存储
    4. 创建 Share 记录并保存
    5. 返回分享信息
    """
    # 验证对象存在且属于当前用户
    obj = await Object.get(session, Object.id == request.object_id)
    if not obj or obj.owner_id != user.id:
        raise HTTPException(status_code=404, detail="对象不存在或无权限")

    # 生成分享码
    code = str(uuid4())

    # 密码加密处理（如果有）
    hashed_password = None
    if request.password:
        hashed_password = Password.hash(request.password)

    # 创建分享记录
    share = Share(
        code=code,
        password=hashed_password,
        object_id=request.object_id,
        user_id=user.id,
        expires=request.expires,
        remain_downloads=request.remain_downloads,
        preview_enabled=request.preview_enabled,
        score=request.score,
        source_name=obj.name,
    )
    share = await share.save(session)

    l.info(f"用户 {user.id} 创建分享: {share.code}")

    # 返回响应
    return ShareResponse(
        id=share.id,
        code=share.code,
        object_id=share.object_id,
        source_name=share.source_name,
        views=share.views,
        downloads=share.downloads,
        remain_downloads=share.remain_downloads,
        expires=share.expires,
        preview_enabled=share.preview_enabled,
        score=share.score,
        created_at=share.created_at,
        is_expired=share.expires is not None and share.expires < datetime.now(),
        has_password=share.password is not None,
    )

@share_router.get(
    path='/',
    summary='列出我的分享',
    description='Get a list of shares.',
)
async def router_share_list(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=100),
    desc: bool = Query(default=True),
    order: Literal["created_at", "updated_at"] = Query(default="created_at"),
    keyword: str | None = Query(default=None),
    expired: bool | None = Query(default=None),
) -> ListResponse[ShareResponse]:
    """
    列出我的分享

    认证：需要 JWT token

    支持：
    - 分页和排序
    - 关键字搜索（搜索 source_name）
    - 过期状态筛选
    """
    # 构建基础条件
    condition = Share.user_id == user.id

    # 关键字搜索
    if keyword:
        condition = condition & Share.source_name.ilike(f"%{keyword}%")

    # 过期状态筛选
    now = datetime.now()
    if expired is True:
        # 已过期：expires 不为 NULL 且 < 当前时间
        condition = condition & (Share.expires != None) & (Share.expires < now)
    elif expired is False:
        # 未过期：expires 为 NULL 或 >= 当前时间
        condition = condition & ((Share.expires == None) | (Share.expires >= now))

    # 构建 table_view
    table_view = TableViewRequest(
        offset=offset,
        limit=limit,
        desc=desc,
        order=order,
    )

    # 使用 get_with_count 获取分页数据
    result = await Share.get_with_count(
        session,
        condition,
        table_view=table_view,
    )

    # 转换为响应模型
    items = [
        ShareResponse(
            id=share.id,
            code=share.code,
            object_id=share.object_id,
            source_name=share.source_name,
            views=share.views,
            downloads=share.downloads,
            remain_downloads=share.remain_downloads,
            expires=share.expires,
            preview_enabled=share.preview_enabled,
            score=share.score,
            created_at=share.created_at,
            is_expired=share.expires is not None and share.expires < now,
            has_password=share.password is not None,
        )
        for share in result.items
    ]

    return ListResponse(count=result.count, items=items)

@share_router.post(
    path='/save/{id}',
    summary='转存他人分享',
    description='Save another user\'s share by ID.',
    dependencies=[Depends(auth_required)]
)
def router_share_save(id: str) -> ResponseBase:
    """
    Save another user's share by ID.
    
    Args:
        id (str): The ID of the share to be saved.
    
    Returns:
        ResponseBase: A model containing the response data for the saved share.
    """
    http_exceptions.raise_not_implemented()

@share_router.patch(
    path='/{id}',
    summary='更新分享信息',
    description='Update share information by ID.',
    dependencies=[Depends(auth_required)]
)
def router_share_update(id: str) -> ResponseBase:
    """
    Update share information by ID.
    
    Args:
        id (str): The ID of the share to be updated.
    
    Returns:
        ResponseBase: A model containing the response data for the updated share.
    """
    http_exceptions.raise_not_implemented()

@share_router.delete(
    path='/{id}',
    summary='删除分享',
    description='Delete a share by ID.',
    dependencies=[Depends(auth_required)]
)
def router_share_delete(id: str) -> ResponseBase:
    """
    Delete a share by ID.
    
    Args:
        id (str): The ID of the share to be deleted.
    
    Returns:
        ResponseBase: A model containing the response data for the deleted share.
    """
    http_exceptions.raise_not_implemented()