from typing import Annotated, Literal
from uuid import UUID, uuid4
from datetime import datetime

from fastapi import APIRouter, Depends, Query, HTTPException
from loguru import logger as l

from middleware.auth import auth_required
from middleware.dependencies import SessionDep
from sqlmodels import ResponseBase
from sqlmodels.user import User
from sqlmodels.share import (
    Share, ShareCreateRequest, CreateShareResponse, ShareResponse,
    ShareDetailResponse, ShareOwnerInfo, ShareObjectItem,
)
from sqlmodels.file import File, FileType
from sqlmodel_ext import ListResponse, TableViewRequest
from utils import http_exceptions
from utils.password.pwd import Password, PasswordStatus

share_router = APIRouter(
    prefix='/share',
    tags=["share"],
)

@share_router.get(
    path='/{id}',
    summary='获取分享详情',
    description='Get share detail by share ID. No authentication required.',
)
async def router_share_get(
    session: SessionDep,
    id: UUID,
    password: str | None = Query(default=None),
) -> ShareDetailResponse:
    """
    获取分享详情

    认证：无需登录

    流程：
    1. 通过分享ID查找分享
    2. 检查过期、封禁状态
    3. 验证提取码（如果有）
    4. 返回分享详情（含文件树和分享者信息）
    """
    # 1. 查询分享（预加载 user 和 object）
    share = await Share.get_exist_one(session, id, load=[Share.user, Share.object])

    # 2. 检查过期
    now = datetime.now()
    if share.expires and share.expires < now:
        http_exceptions.raise_not_found(detail="分享已过期")

    # 3. 获取关联对象
    obj = await share.awaitable_attrs.object
    user = await share.awaitable_attrs.user

    # 4. 检查封禁和软删除
    if obj and obj.is_banned:
        http_exceptions.raise_banned()
    if obj and obj.deleted_at:
        http_exceptions.raise_not_found(detail="分享关联的文件已被删除")

    # 5. 检查密码
    if share.password:
        if not password:
            http_exceptions.raise_precondition_required(detail="请输入提取码")
        if Password.verify(share.password, password) != PasswordStatus.VALID:
            http_exceptions.raise_forbidden(detail="提取码错误")

    # 6. 加载子对象（目录分享）
    children_items: list[ShareObjectItem] = []
    if obj and obj.type == FileType.FOLDER:
        children = await File.get_children(session, obj.owner_id, obj.id)
        children_items = [
            ShareObjectItem(
                id=child.id,
                name=child.name,
                type=child.type,
                size=child.size,
                created_at=child.created_at,
                updated_at=child.updated_at,
            )
            for child in children
        ]

    # 7. 构建响应（在 save 之前，避免 MissingGreenlet）
    response = ShareDetailResponse(
        expires=share.expires,
        preview_enabled=share.preview_enabled,
        score=share.score,
        created_at=share.created_at,
        owner=ShareOwnerInfo(
            nickname=user.nickname if user else None,
            avatar=user.avatar if user else "default",
        ),
        object=ShareObjectItem(
            id=obj.id,
            name=obj.name,
            type=obj.type,
            size=obj.size,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        ),
        children=children_items,
    )

    # 8. 递增浏览次数（最后执行，避免 MissingGreenlet）
    share.views += 1
    await share.save(session, refresh=False)

    return response

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
) -> CreateShareResponse:
    """
    创建新分享

    认证：需要 JWT token

    流程：
    1. 验证对象存在且属于当前用户
    2. 生成随机分享码（uuid4）
    3. 如果有密码则加密存储
    4. 创建 Share 记录并保存
    5. 返回分享 ID
    """
    # 验证对象存在且属于当前用户（排除已删除的）
    obj = await File.get(
        session,
        (File.id == request.file_id) & (File.deleted_at == None)
    )
    if not obj or obj.owner_id != user.id:
        raise HTTPException(status_code=404, detail="对象不存在或无权限")

    if obj.is_banned:
        http_exceptions.raise_banned()

    # 生成分享码
    code = str(uuid4())

    # 密码加密处理（如果有）
    hashed_password = None
    if request.password:
        hashed_password = Password.hash(request.password)

    # 创建分享记录
    user_id = user.id
    share = Share(
        code=code,
        password=hashed_password,
        file_id=request.file_id,
        user_id=user_id,
        expires=request.expires,
        remain_downloads=request.remain_downloads,
        preview_enabled=request.preview_enabled,
        score=request.score,
        source_name=obj.name,
    )
    share = await share.save(session)

    l.info(f"用户 {user_id} 创建分享: {share.code}")

    return CreateShareResponse(share_id=share.id)

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
            file_id=share.file_id,
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
    status_code=204,
)
async def router_share_delete(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    id: UUID,
) -> None:
    """
    删除分享

    认证：需要 JWT token

    流程：
    1. 通过分享ID查找分享
    2. 验证分享属于当前用户
    3. 删除分享记录
    """
    share = await Share.get_exist_one(session, id)
    if share.user_id != user.id:
        http_exceptions.raise_forbidden(detail="无权删除此分享")

    user_id = user.id
    share_code = share.code
    await Share.delete(session, share)

    l.info(f"用户 {user_id} 删除了分享: {share_code}")