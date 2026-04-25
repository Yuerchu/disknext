"""
WOPI 文件操作端点

实现 WOPI 协议的核心文件操作接口：
- CheckFileInfo: 获取文件元数据
- GetFile: 下载文件内容
- PutFile: 上传/更新文件内容
"""
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse
from loguru import logger as l
from sqlmodel_ext import cond

from middleware.dependencies import SessionDep
from sqlmodels import Entry, EntryType, PhysicalFile, Policy, User, WopiFileInfo
from utils.storage import create_storage_driver
from utils import http_exceptions
from utils.JWT.wopi_token import verify_wopi_token

wopi_files_router = APIRouter(prefix="/files", tags=["wopi"])


@wopi_files_router.get(
    path='/{file_id}',
    summary='WOPI CheckFileInfo',
    description='返回文件的元数据信息。',
)
async def check_file_info(
    session: SessionDep,
    file_id: UUID,
    access_token: str = Query(...),
) -> JSONResponse:
    """
    WOPI CheckFileInfo 端点

    认证：WOPI access_token（query 参数）

    返回 WOPI 规范的 PascalCase JSON。
    """
    # 验证令牌 [TODO] 丢到依赖注入里去验证
    payload = verify_wopi_token(access_token)
    if not payload or payload.file_id != file_id:
        http_exceptions.raise_unauthorized("WOPI token 无效或文件不匹配")

    # 获取文件
    file_obj: Entry | None = await Entry.get(
        session,
        cond(Entry.id == file_id),
    )
    if not file_obj or not file_obj.type == EntryType.FILE:
        http_exceptions.raise_not_found("文件不存在")

    # 获取用户信息
    user: User | None = await User.get(session, User.id == payload.user_id)
    user_name = user.nickname or user.email or str(payload.user_id) if user else str(payload.user_id)

    # 构建响应
    info = WopiFileInfo(
        base_file_name=file_obj.name,
        size=file_obj.size or 0,
        owner_id=str(file_obj.owner_id),
        user_id=str(payload.user_id),
        user_friendly_name=user_name,
        version=file_obj.updated_at.isoformat() if file_obj.updated_at else "",
        user_can_write=payload.can_write,
        read_only=not payload.can_write,
        supports_update=payload.can_write,
    )

    return JSONResponse(content=info.model_dump(by_alias=True))


@wopi_files_router.get(
    path='/{file_id}/contents',
    summary='WOPI GetFile',
    description='返回文件的二进制内容。',
)
async def get_file(
    session: SessionDep,
    file_id: UUID,
    access_token: str = Query(...),
) -> Response:
    """
    WOPI GetFile 端点

    认证：WOPI access_token（query 参数）

    返回文件的原始二进制内容。
    """
    # 验证令牌
    payload = verify_wopi_token(access_token)
    if not payload or payload.file_id != file_id:
        http_exceptions.raise_unauthorized("WOPI token 无效或文件不匹配")

    # 获取文件
    file_obj: Entry | None = await Entry.get(session, Entry.id == file_id)
    if not file_obj or not file_obj.type == EntryType.FILE:
        http_exceptions.raise_not_found("文件不存在")

    # 获取物理文件
    physical_file: PhysicalFile | None = await file_obj.awaitable_attrs.physical_file
    if not physical_file or not physical_file.storage_path:
        http_exceptions.raise_internal_error("文件存储路径丢失")

    # 获取策略
    policy: Policy | None = await Policy.get(session, cond(Policy.id == file_obj.policy_id))
    if not policy:
        http_exceptions.raise_internal_error("存储策略不存在")

    driver = create_storage_driver(policy)
    if not await driver.exists(physical_file.storage_path):
        http_exceptions.raise_not_found("物理文件不存在")

    content = await driver.read(physical_file.storage_path)

    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"X-WOPI-ItemVersion": file_obj.updated_at.isoformat() if file_obj.updated_at else ""},
    )


@wopi_files_router.post(
    path='/{file_id}/contents',
    summary='WOPI PutFile',
    description='更新文件内容。',
)
async def put_file(
    session: SessionDep,
    request: Request,
    file_id: UUID,
    access_token: str = Query(...),
) -> JSONResponse:
    """
    WOPI PutFile 端点

    认证：WOPI access_token（query 参数，需要写权限）

    接收请求体中的文件二进制内容并覆盖存储。
    """
    # 验证令牌
    payload = verify_wopi_token(access_token)
    if not payload or payload.file_id != file_id:
        http_exceptions.raise_unauthorized("WOPI token 无效或文件不匹配")

    if not payload.can_write:
        http_exceptions.raise_forbidden("没有写入权限")

    # 获取文件
    file_obj: Entry | None = await Entry.get(session, Entry.id == file_id)
    if not file_obj or not file_obj.type == EntryType.FILE:
        http_exceptions.raise_not_found("文件不存在")

    # 获取物理文件
    physical_file: PhysicalFile | None = await file_obj.awaitable_attrs.physical_file
    if not physical_file or not physical_file.storage_path:
        http_exceptions.raise_internal_error("文件存储路径丢失")

    # 获取策略
    policy: Policy | None = await Policy.get(session, Policy.id == file_obj.policy_id)
    if not policy:
        http_exceptions.raise_internal_error("存储策略不存在")

    # 读取请求体
    content = await request.body()

    driver = create_storage_driver(policy)
    _ = await driver.write(physical_file.storage_path, content)

    # 更新文件大小
    new_size = len(content)
    old_size = file_obj.size or 0
    file_obj.size = new_size
    file_obj = await file_obj.save(session, commit=False)

    # 更新物理文件大小
    physical_file.size = new_size
    _ = await physical_file.save(session, commit=False)

    # 更新用户存储配额
    size_diff = new_size - old_size
    if size_diff != 0:
        from sqlmodels.user import User
        owner = await User.get(session, User.id == file_obj.owner_id)
        if owner:
            await owner.adjust_storage(session, size_diff, commit=False)

    await session.commit()

    l.info(f"WOPI PutFile: file_id={file_id}, new_size={new_size}")

    return JSONResponse(
        content={"ItemVersion": file_obj.updated_at.isoformat() if file_obj.updated_at else ""},
        status_code=200,
    )
