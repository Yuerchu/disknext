"""
文件分类筛选端点

按文件类型分类（图片/视频/音频/文档）查询用户的所有文件，
跨目录搜索，支持分页。扩展名映射从数据库 Setting 表读取。
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger as l

from middleware.auth import auth_required
from middleware.dependencies import SessionDep, TableViewRequestDep
from sqlmodels import (
    FileCategory,
    ListResponse,
    Object,
    ObjectResponse,
    ObjectType,
    Setting,
    SettingsType,
    User,
)

category_router = APIRouter(
    prefix="/category",
    tags=["category"],
)


@category_router.get(
    path="/{category}",
    summary="按分类获取文件列表",
)
async def router_category_list(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    category: FileCategory,
    table_view: TableViewRequestDep,
) -> ListResponse[ObjectResponse]:
    """
    按文件类型分类查询用户的所有文件

    跨所有目录搜索，返回分页结果。
    扩展名配置从数据库 Setting 表读取（type=file_category）。

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
    - ListResponse[ObjectResponse]: 分页文件列表

    错误处理：
    - HTTPException 422: category 参数无效
    - HTTPException 404: 该分类未配置扩展名
    """
    # 从数据库读取该分类的扩展名配置
    setting = await Setting.get(
        session,
        (Setting.type == SettingsType.FILE_CATEGORY) & (Setting.name == category.value),
    )
    if not setting or not setting.value:
        raise HTTPException(status_code=404, detail=f"分类 {category.value} 未配置扩展名")

    extensions = [ext.strip() for ext in setting.value.split(",") if ext.strip()]
    if not extensions:
        raise HTTPException(status_code=404, detail=f"分类 {category.value} 扩展名列表为空")

    result = await Object.get_by_category(
        session,
        user.id,
        extensions,
        table_view=table_view,
    )

    items = [
        ObjectResponse(
            id=obj.id,
            name=obj.name,
            type=ObjectType.FILE,
            size=obj.size,
            mime_type=obj.mime_type,
            thumb=False,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
            source_enabled=False,
        )
        for obj in result.items
    ]

    return ListResponse(count=result.count, items=items)
