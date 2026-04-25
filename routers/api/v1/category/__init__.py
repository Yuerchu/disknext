"""
文件分类筛选端点

按文件类型分类（图片/视频/音频/文档）查询用户的所有文件，
跨目录搜索，支持分页。扩展名映射从 ServerConfig 读取。
"""
from typing import Annotated

from fastapi import APIRouter, Depends

from middleware.auth import auth_required
from middleware.dependencies import SessionDep, ServerConfigDep, TableViewRequestDep
from sqlmodels import (
    FileCategory,
    ListResponse,
    Entry,
    EntryResponse,
    EntryType,
    User,
)
from utils import http_exceptions
from utils.http.error_codes import ErrorCode as E

category_router = APIRouter(
    prefix="/category",
    tags=["category"],
    deprecated=True,  # [TODO] 使用 /search?category=xxx 替代
)


@category_router.get(
    path="/{category}",
    summary="按分类获取文件列表",
)
async def router_category_list(
    session: SessionDep,
    config: ServerConfigDep,
    user: Annotated[User, Depends(auth_required)],
    category: FileCategory,
    table_view: TableViewRequestDep,
) -> ListResponse[EntryResponse]:
    """
    按文件类型分类查询用户的所有文件

    跨所有目录搜索，返回分页结果。
    扩展名配置从 ServerConfig 读取。

    认证：
    - JWT token in Authorization header

    路径参数：
    - category: 文件分类（image / video / audio / document）

    查询参数：
    - offset: 分页偏移量（默认0）
    - limit: 每页数量（默认20，最大100）
    - desc: 是否降序（默认true）
    - order: 排序字段（created_at / updated_at）

    响应：
    - ListResponse[EntryResponse]: 分页文件列表

    错误处理：
    - HTTPException 422: category 参数无效
    - HTTPException 404: 该分类未配置扩展名
    """
    # 从 ServerConfig 读取该分类的扩展名配置
    category_attr_map = {
        FileCategory.IMAGE: config.file_category_image,
        FileCategory.VIDEO: config.file_category_video,
        FileCategory.AUDIO: config.file_category_audio,
        FileCategory.DOCUMENT: config.file_category_document,
    }
    extensions_str = category_attr_map.get(category)
    if not extensions_str:
        http_exceptions.raise_not_found(E.CATEGORY_NOT_CONFIGURED, f"分类 {category.value} 未配置扩展名")

    extensions = [ext.strip() for ext in extensions_str.split(",") if ext.strip()]
    if not extensions:
        http_exceptions.raise_not_found(E.CATEGORY_NOT_CONFIGURED, f"分类 {category.value} 扩展名列表为空")

    result = await Entry.get_by_category(
        session,
        user.id,
        extensions,
        table_view=table_view,
    )

    items = [
        EntryResponse.model_validate(obj, from_attributes=True, update={
            'type': EntryType.FILE,
        })
        for obj in result.items
    ]

    return ListResponse(count=result.count, items=items)
