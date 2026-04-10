"""
文件操作路由

提供文件上传、下载、创建等核心功能。

路由结构：
- /file - 文件操作
- /file/upload - 上传相关操作
- /file/download - 下载相关操作
"""
import hashlib
from datetime import datetime, timedelta
from typing import Annotated
from uuid import UUID

import orjson
import whatthepatch
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from starlette.responses import Response
from loguru import logger as l
from sqlmodel_ext import SQLModelBase
from whatthepatch.exceptions import HunkApplyException

from middleware.auth import auth_required, verify_download_token
from middleware.dependencies import SessionDep, ServerConfigDep
from sqlmodels import (
    CreateFileRequest,
    CreateUploadSessionRequest,
    FileApp,
    FileAppExtension,
    FileAppGroupLink,
    FileAppType,
    Object,
    ObjectType,
    PhysicalFile,
    Policy,
    PolicyType,
    ResponseBase,
    SourceLink,
    UploadChunkResponse,
    UploadSession,
    UploadSessionResponse,
    User,
    WopiSessionResponse,
)
import orjson

from service.storage import LocalStorageService, S3StorageService, adjust_user_storage
from utils.JWT import create_download_token, DOWNLOAD_TOKEN_TTL
from utils.JWT.wopi_token import create_wopi_token
from utils import http_exceptions
from .viewers import viewers_router


# DTO

class DownloadTokenModel(ResponseBase):
    """下载Token响应模型"""

    access_token: str
    """JWT 令牌"""

    expires_in: int
    """过期时间（秒）"""


class TextContentResponse(ResponseBase):
    """文本文件内容响应"""

    content: str
    """文件文本内容（UTF-8）"""

    hash: str
    """SHA-256 hex"""

    size: int
    """文件字节大小"""


class PatchContentRequest(SQLModelBase):
    """增量保存请求"""

    patch: str
    """unified diff 文本"""

    base_hash: str
    """原始内容的 SHA-256 hex（64字符）"""


class PatchContentResponse(ResponseBase):
    """增量保存响应"""

    new_hash: str
    """新内容的 SHA-256 hex"""

    new_size: int
    """新文件字节大小"""


class SourceLinkResponse(ResponseBase):
    """外链响应"""

    url: str
    """外链地址（永久有效，/source/ 端点自动 302 适配存储策略）"""

    downloads: int
    """历史下载次数"""


def _check_policy_size_limit(policy: Policy, file_size: int) -> None:
    """
    检查文件大小是否超过策略限制

    :param policy: 存储策略
    :param file_size: 文件大小（字节）
    :raises HTTPException: 413 Payload Too Large
    """
    if policy.max_size > 0 and file_size > policy.max_size:
        raise HTTPException(
            status_code=413,
            detail=f"文件大小超过限制 ({policy.max_size} bytes)",
        )


# ==================== 主路由 ====================

router = APIRouter(prefix="/file", tags=["file"])


# ==================== 上传子路由 ====================

_upload_router = APIRouter(prefix="/upload")


@_upload_router.put(
    path='/',
    summary='创建上传会话',
    description='创建文件上传会话，返回会话ID用于后续分片上传。',
)
async def create_upload_session(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    request: CreateUploadSessionRequest,
) -> UploadSessionResponse:
    """
    创建上传会话端点

    流程：
    1. 验证父目录存在且属于当前用户
    2. 确定存储策略（使用指定的或继承父目录的）
    3. 验证文件大小限制
    4. 创建上传会话并生成存储路径
    5. 返回会话信息
    """
    # 验证文件名
    if not request.file_name or '/' in request.file_name or '\\' in request.file_name:
        raise HTTPException(status_code=400, detail="无效的文件名")

    # 验证父目录（排除已删除的）
    parent = await Object.get(
        session,
        (Object.id == request.parent_id) & (Object.deleted_at == None)
    )
    if not parent or parent.owner_id != user.id:
        raise HTTPException(status_code=404, detail="父目录不存在")

    if not parent.is_folder:
        raise HTTPException(status_code=400, detail="父对象不是目录")

    if parent.is_banned:
        http_exceptions.raise_banned("目标目录已被封禁，无法执行此操作")

    # 确定存储策略
    policy_id = request.policy_id or parent.policy_id
    policy = await Policy.get_exist_one(session, policy_id)

    # 校验用户组是否有权使用该策略（仅当用户显式指定 policy_id 时）
    if request.policy_id:
        group = await user.awaitable_attrs.group
        await session.refresh(group, ['policies'])
        if request.policy_id not in {p.id for p in group.policies}:
            raise HTTPException(status_code=403, detail="当前用户组无权使用该存储策略")

    # 验证文件大小限制
    _check_policy_size_limit(policy, request.file_size)

    # 检查存储配额（auth_required 已预加载 user.group）
    max_storage = user.group.max_storage
    if max_storage > 0 and user.storage + request.file_size > max_storage:
        http_exceptions.raise_insufficient_quota("存储空间不足")

    # 检查是否已存在同名文件（仅检查未删除的）
    existing = await Object.get(
        session,
        (Object.owner_id == user.id) &
        (Object.parent_id == parent.id) &
        (Object.name == request.file_name) &
        (Object.deleted_at == None)
    )
    if existing:
        raise HTTPException(status_code=409, detail="同名文件已存在")

    # 计算分片信息
    options = await policy.awaitable_attrs.options
    chunk_size = options.chunk_size if options else 52428800  # 默认 50MB
    total_chunks = max(1, (request.file_size + chunk_size - 1) // chunk_size) if request.file_size > 0 else 1

    # 生成存储路径
    storage_path: str | None = None
    s3_upload_id: str | None = None
    if policy.type == PolicyType.LOCAL:
        storage_service = LocalStorageService(policy)
        dir_path, storage_name, full_path = await storage_service.generate_file_path(
            user_id=user.id,
            original_filename=request.file_name,
        )
        storage_path = full_path
    elif policy.type == PolicyType.S3:
        s3_service = S3StorageService(
            policy,
            region=options.s3_region if options else 'us-east-1',
            is_path_style=options.s3_path_style if options else False,
        )
        dir_path, storage_name, storage_path = await s3_service.generate_file_path(
            user_id=user.id,
            original_filename=request.file_name,
        )
        # 多分片时创建 multipart upload
        if total_chunks > 1:
            s3_upload_id = await s3_service.create_multipart_upload(
                storage_path, content_type='application/octet-stream',
            )

    # 预扣存储空间（与创建会话在同一事务中提交，防止并发绕过配额）
    if request.file_size > 0:
        await adjust_user_storage(session, user.id, request.file_size, commit=False)

    # 创建上传会话
    upload_session = UploadSession(
        file_name=request.file_name,
        file_size=request.file_size,
        chunk_size=chunk_size,
        total_chunks=total_chunks,
        storage_path=storage_path,
        s3_upload_id=s3_upload_id,
        expires_at=datetime.now() + timedelta(hours=24),
        owner_id=user.id,
        parent_id=request.parent_id,
        policy_id=policy_id,
    )
    upload_session = await upload_session.save(session)

    l.info(f"创建上传会话: {upload_session.id}, 文件: {request.file_name}, 大小: {request.file_size}")

    return UploadSessionResponse(
        id=upload_session.id,
        file_name=upload_session.file_name,
        file_size=upload_session.file_size,
        chunk_size=upload_session.chunk_size,
        total_chunks=upload_session.total_chunks,
        uploaded_chunks=0,
        expires_at=upload_session.expires_at,
    )


@_upload_router.post(
    path='/{session_id}/{chunk_index}',
    summary='上传文件分片',
    description='上传指定分片，分片索引从0开始。',
)
async def upload_chunk(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    session_id: UUID,
    chunk_index: int,
    file: UploadFile = File(...),
) -> UploadChunkResponse:
    """
    上传文件分片端点

    流程：
    1. 验证上传会话
    2. 写入分片数据
    3. 更新会话进度
    4. 如果所有分片上传完成，创建 Object 记录
    """
    # 获取上传会话
    upload_session = await UploadSession.get(session, UploadSession.id == session_id)
    if not upload_session or upload_session.owner_id != user.id:
        raise HTTPException(status_code=404, detail="上传会话不存在")

    if upload_session.is_expired:
        raise HTTPException(status_code=400, detail="上传会话已过期")

    # 存储 user.id，避免后续 save() 导致 user 过期后无法访问
    user_id = user.id

    if chunk_index < 0 or chunk_index >= upload_session.total_chunks:
        raise HTTPException(status_code=400, detail="无效的分片索引")

    # 获取策略
    policy = await Policy.get(session, Policy.id == upload_session.policy_id)
    if not policy:
        raise HTTPException(status_code=500, detail="存储策略不存在")

    # 读取分片内容
    content = await file.read()

    # 写入分片
    if policy.type == PolicyType.LOCAL:
        if not upload_session.storage_path:
            raise HTTPException(status_code=500, detail="存储路径丢失")

        storage_service = LocalStorageService(policy)
        offset = chunk_index * upload_session.chunk_size
        await storage_service.write_file_chunk(
            upload_session.storage_path,
            content,
            offset,
        )
    elif policy.type == PolicyType.S3:
        if not upload_session.storage_path:
            raise HTTPException(status_code=500, detail="存储路径丢失")

        s3_service = await S3StorageService.from_policy(policy)

        if upload_session.total_chunks == 1:
            # 单分片：直接 PUT 上传
            await s3_service.upload_file(upload_session.storage_path, content)
        else:
            # 多分片：UploadPart
            if not upload_session.s3_upload_id:
                raise HTTPException(status_code=500, detail="S3 分片上传 ID 丢失")

            etag = await s3_service.upload_part(
                upload_session.storage_path,
                upload_session.s3_upload_id,
                chunk_index + 1,  # S3 part number 从 1 开始
                content,
            )
            # 追加 ETag 到 s3_part_etags
            etags: list[list[int | str]] = orjson.loads(upload_session.s3_part_etags or '[]')
            etags.append([chunk_index + 1, etag])
            upload_session.s3_part_etags = orjson.dumps(etags).decode()

    # 在 save（commit）前缓存后续需要的属性（commit 后 ORM 对象会过期）
    policy_type = policy.type
    s3_upload_id = upload_session.s3_upload_id
    s3_part_etags = upload_session.s3_part_etags
    s3_service_for_complete: S3StorageService | None = None
    if policy_type == PolicyType.S3:
        s3_service_for_complete = await S3StorageService.from_policy(policy)

    # 更新会话进度
    upload_session.uploaded_chunks += 1
    upload_session.uploaded_size += len(content)
    upload_session = await upload_session.save(session)

    # 在后续可能的 commit 前保存需要的属性
    is_complete = upload_session.is_complete
    uploaded_chunks = upload_session.uploaded_chunks
    total_chunks = upload_session.total_chunks
    file_object_id: UUID | None = None

    if is_complete:
        # 保存 upload_session 属性（commit 后会过期）
        file_name = upload_session.file_name
        file_size = upload_session.file_size
        uploaded_size = upload_session.uploaded_size
        storage_path = upload_session.storage_path
        upload_session_id = upload_session.id
        parent_id = upload_session.parent_id
        policy_id = upload_session.policy_id

        # S3 多分片上传完成：合并分片
        if (
            policy_type == PolicyType.S3
            and s3_upload_id
            and s3_part_etags
            and s3_service_for_complete
        ):
            parts_data: list[list[int | str]] = orjson.loads(s3_part_etags)
            parts = [(int(pn), str(et)) for pn, et in parts_data]
            await s3_service_for_complete.complete_multipart_upload(
                storage_path, s3_upload_id, parts,
            )

        # 创建 PhysicalFile 记录
        physical_file = PhysicalFile(
            storage_path=storage_path,
            size=uploaded_size,
            policy_id=policy_id,
            reference_count=1,
        )
        physical_file = await physical_file.save(session, commit=False)

        # 创建 Object 记录
        file_object = Object(
            name=file_name,
            type=ObjectType.FILE,
            size=uploaded_size,
            physical_file_id=physical_file.id,
            upload_session_id=str(upload_session_id),
            parent_id=parent_id,
            owner_id=user_id,
            policy_id=policy_id,
        )
        file_object = await file_object.save(session, commit=False)
        file_object_id = file_object.id

        # 删除上传会话（使用条件删除）
        await UploadSession.delete(
            session,
            condition=UploadSession.id == upload_session_id,
            commit=False
        )

        # 调整存储配额差值（创建会话时已预扣 file_size，这里只补差）
        size_diff = uploaded_size - file_size
        if size_diff != 0:
            await adjust_user_storage(session, user_id, size_diff, commit=False)

        # 统一提交所有更改
        await session.commit()

        l.info(f"文件上传完成: {file_name}, size={uploaded_size}, id={file_object_id}")

    return UploadChunkResponse(
        uploaded_chunks=uploaded_chunks if not is_complete else total_chunks,
        total_chunks=total_chunks,
        is_complete=is_complete,
        object_id=file_object_id,
    )


@_upload_router.delete(
    path='/{session_id}',
    summary='删除上传会话',
    description='取消上传并删除会话及已上传的临时文件。',
    status_code=204,
)
async def delete_upload_session(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    session_id: UUID,
) -> None:
    """删除上传会话端点"""
    upload_session = await UploadSession.get(session, UploadSession.id == session_id)
    if not upload_session or upload_session.owner_id != user.id:
        raise HTTPException(status_code=404, detail="上传会话不存在")

    # 删除临时文件
    policy = await Policy.get(session, Policy.id == upload_session.policy_id)
    if policy and upload_session.storage_path:
        if policy.type == PolicyType.LOCAL:
            storage_service = LocalStorageService(policy)
            await storage_service.delete_file(upload_session.storage_path)
        elif policy.type == PolicyType.S3:
            s3_service = await S3StorageService.from_policy(policy)
            # 如果有分片上传，先取消
            if upload_session.s3_upload_id:
                await s3_service.abort_multipart_upload(
                    upload_session.storage_path, upload_session.s3_upload_id,
                )
            else:
                # 单分片上传已完成的话，删除已上传的文件
                if upload_session.uploaded_chunks > 0:
                    await s3_service.delete_file(upload_session.storage_path)

    # 释放预扣的存储空间
    if upload_session.file_size > 0:
        await adjust_user_storage(session, user.id, -upload_session.file_size)

    # 删除会话记录
    await UploadSession.delete(session, upload_session)

    l.info(f"删除上传会话: {session_id}")


@_upload_router.delete(
    path='/',
    summary='清除所有上传会话',
    description='清除当前用户的所有上传会话。',
    status_code=204,
)
async def clear_upload_sessions(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
) -> None:
    """清除所有上传会话端点"""
    # 获取所有会话
    sessions = await UploadSession.get(
        session,
        UploadSession.owner_id == user.id,
        fetch_mode="all"
    )

    deleted_count = 0
    for upload_session in sessions:
        # 删除临时文件
        policy = await Policy.get(session, Policy.id == upload_session.policy_id)
        if policy and upload_session.storage_path:
            if policy.type == PolicyType.LOCAL:
                storage_service = LocalStorageService(policy)
                await storage_service.delete_file(upload_session.storage_path)
            elif policy.type == PolicyType.S3:
                s3_service = await S3StorageService.from_policy(policy)
                if upload_session.s3_upload_id:
                    await s3_service.abort_multipart_upload(
                        upload_session.storage_path, upload_session.s3_upload_id,
                    )
                elif upload_session.uploaded_chunks > 0:
                    await s3_service.delete_file(upload_session.storage_path)

        # 释放预扣的存储空间
        if upload_session.file_size > 0:
            await adjust_user_storage(session, user.id, -upload_session.file_size)

        await UploadSession.delete(session, upload_session)
        deleted_count += 1

    l.info(f"清除用户 {user.id} 的所有上传会话，共 {deleted_count} 个")


@_upload_router.get(
    path='/archive/{session_id}/archive.zip',
    summary='打包并下载文件',
    description='获取打包后的文件。',
)
async def download_archive(session_id: str) -> ResponseBase:
    """打包下载"""
    raise HTTPException(status_code=501, detail="打包下载功能暂未实现")


# ==================== 下载子路由 ====================

_download_router = APIRouter(prefix="/download")


@_download_router.post(
    path='/{file_id}',
    summary='创建下载令牌',
    description='为指定文件创建下载令牌（JWT），有效期1小时。',
)
async def create_download_token_endpoint(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    file_id: UUID,
) -> DownloadTokenModel:
    """
    创建下载令牌端点

    验证文件存在且属于当前用户后，生成 JWT 下载令牌。
    """
    file_obj = await Object.get(
        session,
        (Object.id == file_id) & (Object.deleted_at == None)
    )
    if not file_obj or file_obj.owner_id != user.id:
        raise HTTPException(status_code=404, detail="文件不存在")

    if not file_obj.is_file:
        raise HTTPException(status_code=400, detail="对象不是文件")

    if file_obj.is_banned:
        http_exceptions.raise_banned()

    token = create_download_token(file_id, user.id)

    l.debug(f"创建下载令牌: file_id={file_id}, user_id={user.id}")

    return DownloadTokenModel(access_token=token, expires_in=int(DOWNLOAD_TOKEN_TTL.total_seconds()))


@_download_router.get(
    path='/{token}',
    summary='下载文件',
    description='使用下载令牌下载文件，令牌在有效期内可重复使用。',
    response_model=None,
)
async def download_file(
    session: SessionDep,
    token: str,
) -> Response:
    """
    下载文件端点

    验证 JWT 令牌后返回文件内容。
    令牌在有效期内可重复使用（支持浏览器 range 请求等场景）。
    """
    # 验证令牌
    result = verify_download_token(token)
    if not result:
        raise HTTPException(status_code=401, detail="下载令牌无效或已过期")

    _, file_id, owner_id = result

    # 获取文件对象（排除已删除的），同时预加载 physical_file 关系
    file_obj = await Object.get(
        session,
        (Object.id == file_id) & (Object.deleted_at == None),
        load=Object.physical_file,
    )
    if not file_obj or file_obj.owner_id != owner_id:
        raise HTTPException(status_code=404, detail="文件不存在")

    if not file_obj.is_file:
        raise HTTPException(status_code=400, detail="对象不是文件")

    if file_obj.is_banned:
        http_exceptions.raise_banned()

    physical_file = file_obj.physical_file
    if not physical_file or not physical_file.storage_path:
        raise HTTPException(status_code=500, detail="文件存储路径丢失")

    storage_path = physical_file.storage_path

    # 获取策略
    policy = await Policy.get(session, Policy.id == file_obj.policy_id)
    if not policy:
        raise HTTPException(status_code=500, detail="存储策略不存在")

    if policy.type == PolicyType.LOCAL:
        storage_service = LocalStorageService(policy)
        if not await storage_service.file_exists(storage_path):
            raise HTTPException(status_code=404, detail="物理文件不存在")

        return FileResponse(
            path=storage_path,
            filename=file_obj.name,
            media_type="application/octet-stream",
        )
    elif policy.type == PolicyType.S3:
        s3_service = await S3StorageService.from_policy(policy)
        # 302 重定向到预签名 URL
        presigned_url = s3_service.generate_presigned_url(
            storage_path, method='GET', expires_in=3600, filename=file_obj.name,
        )
        return RedirectResponse(url=presigned_url, status_code=302)
    else:
        raise HTTPException(status_code=500, detail="不支持的存储类型")


# ==================== 包含子路由 ====================

router.include_router(_upload_router)
router.include_router(_download_router)
router.include_router(viewers_router)


# ==================== 创建空白文件 ====================

@router.post(
    path='/create',
    summary='创建空白文件',
    description='在指定目录下创建空白文件。',
    status_code=204,
)
async def create_empty_file(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    request: CreateFileRequest,
) -> None:
    """创建空白文件端点"""
    # 存储 user.id，避免后续 save() 导致 user 过期后无法访问
    user_id = user.id

    # 验证文件名
    if not request.name or '/' in request.name or '\\' in request.name:
        raise HTTPException(status_code=400, detail="无效的文件名")

    # 验证父目录（排除已删除的）
    parent = await Object.get(
        session,
        (Object.id == request.parent_id) & (Object.deleted_at == None)
    )
    if not parent or parent.owner_id != user_id:
        raise HTTPException(status_code=404, detail="父目录不存在")

    if not parent.is_folder:
        raise HTTPException(status_code=400, detail="父对象不是目录")

    if parent.is_banned:
        http_exceptions.raise_banned("目标目录已被封禁，无法执行此操作")

    # 检查是否已存在同名文件（仅检查未删除的）
    existing = await Object.get(
        session,
        (Object.owner_id == user_id) &
        (Object.parent_id == parent.id) &
        (Object.name == request.name) &
        (Object.deleted_at == None)
    )
    if existing:
        raise HTTPException(status_code=409, detail="同名文件已存在")

    # 确定存储策略
    policy_id = request.policy_id or parent.policy_id
    policy = await Policy.get_exist_one(session, policy_id)

    # 生成存储路径并创建空文件
    storage_path: str | None = None
    if policy.type == PolicyType.LOCAL:
        storage_service = LocalStorageService(policy)
        dir_path, storage_name, full_path = await storage_service.generate_file_path(
            user_id=user_id,
            original_filename=request.name,
        )
        await storage_service.create_empty_file(full_path)
        storage_path = full_path
    elif policy.type == PolicyType.S3:
        s3_service = await S3StorageService.from_policy(policy)
        dir_path, storage_name, storage_path = await s3_service.generate_file_path(
            user_id=user_id,
            original_filename=request.name,
        )
        await s3_service.upload_file(storage_path, b'')

    # 创建 PhysicalFile 记录
    physical_file = PhysicalFile(
        storage_path=storage_path,
        size=0,
        policy_id=policy_id,
        reference_count=1,
    )
    physical_file = await physical_file.save(session)

    # 创建 Object 记录
    file_object = Object(
        name=request.name,
        type=ObjectType.FILE,
        size=0,
        physical_file_id=physical_file.id,
        parent_id=request.parent_id,
        owner_id=user_id,
        policy_id=policy_id,
    )
    file_object = await file_object.save(session)

    l.info(f"创建空白文件: {file_object.name}, id={file_object.id}")


# ==================== WOPI 会话 ====================

@router.post(
    path='/{file_id}/wopi-session',
    summary='创建 WOPI 会话',
    description='为 WOPI 类型的查看器创建编辑会话，返回编辑器 URL 和访问令牌。',
)
async def create_wopi_session(
    session: SessionDep,
    config: ServerConfigDep,
    user: Annotated[User, Depends(auth_required)],
    file_id: UUID,
) -> WopiSessionResponse:
    """
    创建 WOPI 会话端点

    流程：
    1. 验证文件存在且属于当前用户
    2. 查找文件扩展名对应的 WOPI 类型应用
    3. 检查用户组权限
    4. 生成 WOPI access token
    5. 构建 editor URL

    认证：JWT token 必填

    错误处理：
    - 404: 文件不存在 / 无可用 WOPI 应用
    - 403: 用户组无权限
    """
    # 验证文件
    file_obj: Object | None = await Object.get(
        session,
        Object.id == file_id,
    )
    if not file_obj or file_obj.owner_id != user.id:
        http_exceptions.raise_not_found("文件不存在")

    if not file_obj.is_file:
        http_exceptions.raise_bad_request("对象不是文件")

    # 获取文件扩展名
    name_parts = file_obj.name.rsplit('.', 1)
    if len(name_parts) < 2:
        http_exceptions.raise_bad_request("文件无扩展名，无法使用 WOPI 查看器")
    ext = name_parts[1].lower()

    # 查找 WOPI 类型的应用
    from sqlalchemy import and_, select
    ext_records: list[FileAppExtension] = await FileAppExtension.get(
        session,
        FileAppExtension.extension == ext,
        fetch_mode="all",
        load=FileAppExtension.app,
    )

    wopi_app: FileApp | None = None
    matched_ext_record: FileAppExtension | None = None
    for ext_record in ext_records:
        app = ext_record.app
        if app.type == FileAppType.WOPI and app.is_enabled:
            # 检查用户组权限（FileAppGroupLink 是纯关联表，使用 session 查询）
            if app.is_restricted:
                stmt = select(FileAppGroupLink).where(
                    and_(
                        FileAppGroupLink.app_id == app.id,
                        FileAppGroupLink.group_id == user.group_id,
                    )
                )
                result = await session.exec(stmt)
                if not result.first():
                    continue
            wopi_app = app
            matched_ext_record = ext_record
            break

    if not wopi_app:
        http_exceptions.raise_not_found("无可用的 WOPI 查看器")

    # 优先使用 per-extension URL（Discovery 自动填充），回退到全局模板
    editor_url_template: str | None = None
    if matched_ext_record and matched_ext_record.wopi_action_url:
        editor_url_template = matched_ext_record.wopi_action_url
    if not editor_url_template:
        editor_url_template = wopi_app.wopi_editor_url_template
    if not editor_url_template:
        http_exceptions.raise_bad_request("WOPI 应用未配置编辑器 URL 模板，请先执行 Discovery 或手动配置")

    # 获取站点 URL
    site_url = config.site_url

    # 生成 WOPI token
    can_write = file_obj.owner_id == user.id
    token, access_token_ttl = create_wopi_token(file_id, user.id, can_write)

    # 构建 wopi_src
    wopi_src = f"{site_url}/wopi/files/{file_id}"

    # 构建 editor URL（只替换 wopi_src，token 通过 POST 表单传递）
    editor_url = editor_url_template.format(wopi_src=wopi_src)

    return WopiSessionResponse(
        wopi_src=wopi_src,
        access_token=token,
        access_token_ttl=access_token_ttl,
        editor_url=editor_url,
    )


# ==================== 文件外链（保留原有端点结构） ====================

async def _validate_source_link(
    session: SessionDep,
    file_id: UUID,
) -> tuple[Object, SourceLink, PhysicalFile, Policy]:
    """
    验证外链访问的完整链路

    :returns: (file_obj, link, physical_file, policy)
    :raises HTTPException: 验证失败
    """
    file_obj = await Object.get(
        session,
        (Object.id == file_id) & (Object.deleted_at == None),
        load=Object.physical_file,
    )
    if not file_obj:
        http_exceptions.raise_not_found("文件不存在")

    if not file_obj.is_file:
        http_exceptions.raise_bad_request("对象不是文件")

    if file_obj.is_banned:
        http_exceptions.raise_banned()

    policy = await Policy.get(session, Policy.id == file_obj.policy_id)
    if not policy:
        http_exceptions.raise_internal_error("存储策略不存在")

    if not policy.is_origin_link_enable:
        http_exceptions.raise_forbidden("当前存储策略未启用外链功能")

    # SourceLink 必须存在（只有主动创建过外链的文件才能通过外链访问）
    link: SourceLink | None = await SourceLink.get(
        session,
        SourceLink.object_id == file_id,
    )
    if not link:
        http_exceptions.raise_not_found("外链不存在")

    physical_file = file_obj.physical_file
    if not physical_file or not physical_file.storage_path:
        http_exceptions.raise_internal_error("文件存储路径丢失")

    return file_obj, link, physical_file, policy


@router.get(
    path='/get/{file_id}/{name}',
    summary='文件外链（直接输出文件数据）',
    description='通过外链直接获取文件内容，公开访问无需认证。',
    response_model=None,
)
async def file_get(
    session: SessionDep,
    file_id: UUID,
    name: str,
) -> Response:
    """
    文件外链端点（直接输出）

    公开访问，无需认证。通过 UUID 定位文件，URL 中的 name 仅用于 Content-Disposition。

    错误处理：
    - 403: 存储策略未启用外链 / 文件被封禁
    - 404: 文件不存在 / 外链不存在 / 物理文件不存在
    """
    file_obj, link, physical_file, policy = await _validate_source_link(session, file_id)

    # 缓存物理路径（save 后对象属性会过期）
    file_path = physical_file.storage_path

    # 递增下载次数
    link.downloads += 1
    link = await link.save(session)

    if policy.type == PolicyType.LOCAL:
        storage_service = LocalStorageService(policy)
        if not await storage_service.file_exists(file_path):
            http_exceptions.raise_not_found("物理文件不存在")

        return FileResponse(
            path=file_path,
            filename=name,
            media_type="application/octet-stream",
        )
    elif policy.type == PolicyType.S3:
        # S3 外链直接输出：302 重定向到预签名 URL
        s3_service = await S3StorageService.from_policy(policy)
        presigned_url = s3_service.generate_presigned_url(
            file_path, method='GET', expires_in=3600, filename=name,
        )
        return RedirectResponse(url=presigned_url, status_code=302)
    else:
        http_exceptions.raise_internal_error("不支持的存储类型")


@router.get(
    path='/source/{file_id}/{name}',
    summary='文件外链（302重定向或直接输出）',
    description='通过外链获取文件，公有存储 302 重定向，私有存储直接输出。',
    response_model=None,
)
async def file_source_redirect(
    session: SessionDep,
    file_id: UUID,
    name: str,
) -> Response:
    """
    文件外链端点（重定向/直接输出）

    公开访问，无需认证。根据 policy.is_private 决定服务方式：
    - is_private=False 且 base_url 非空：302 临时重定向
    - is_private=True 或 base_url 为空：直接返回文件内容

    错误处理：
    - 403: 存储策略未启用外链 / 文件被封禁
    - 404: 文件不存在 / 外链不存在 / 物理文件不存在
    """
    file_obj, link, physical_file, policy = await _validate_source_link(session, file_id)

    # 缓存所有需要的值（save 后对象属性会过期）
    file_path = physical_file.storage_path
    is_private = policy.is_private
    base_url = policy.base_url

    # 递增下载次数
    link.downloads += 1
    link = await link.save(session)

    if policy.type == PolicyType.LOCAL:
        storage_service = LocalStorageService(policy)
        if not await storage_service.file_exists(file_path):
            http_exceptions.raise_not_found("物理文件不存在")

        # 公有存储：302 重定向到 base_url
        if not is_private and base_url:
            relative_path = storage_service.get_relative_path(file_path)
            redirect_url = f"{base_url}/{relative_path}"
            return RedirectResponse(url=redirect_url, status_code=302)

        # 私有存储或 base_url 为空：通过应用代理文件
        return FileResponse(
            path=file_path,
            filename=name,
            media_type="application/octet-stream",
        )
    elif policy.type == PolicyType.S3:
        s3_service = await S3StorageService.from_policy(policy)
        # 公有存储且有 base_url：直接重定向到公开 URL
        if not is_private and base_url:
            redirect_url = f"{base_url.rstrip('/')}/{file_path}"
            return RedirectResponse(url=redirect_url, status_code=302)
        # 私有存储：生成预签名 URL 重定向
        presigned_url = s3_service.generate_presigned_url(
            file_path, method='GET', expires_in=3600, filename=name,
        )
        return RedirectResponse(url=presigned_url, status_code=302)
    else:
        http_exceptions.raise_internal_error("不支持的存储类型")


@router.put(
    path='/update/{id}',
    summary='更新文件',
    description='更新文件内容。',
    dependencies=[Depends(auth_required)]
)
async def file_update(id: str) -> ResponseBase:
    """更新文件内容"""
    raise HTTPException(status_code=501, detail="更新文件功能暂未实现")


@router.get(
    path='/content/{file_id}',
    summary='获取文本文件内容',
    description='获取文本文件的 UTF-8 内容和 SHA-256 哈希值。',
)
async def file_content(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    file_id: UUID,
) -> TextContentResponse:
    """
    获取文本文件内容端点

    返回文件的 UTF-8 文本内容和基于规范化内容的 SHA-256 哈希值。
    换行符统一规范化为 ``\\n``。

    认证：JWT token 必填

    错误处理：
    - 400: 文件不是有效的 UTF-8 文本
    - 404: 文件不存在
    """
    file_obj = await Object.get(
        session,
        (Object.id == file_id) & (Object.deleted_at == None),
        load=Object.physical_file,
    )
    if not file_obj or file_obj.owner_id != user.id:
        http_exceptions.raise_not_found("文件不存在")

    if not file_obj.is_file:
        http_exceptions.raise_bad_request("对象不是文件")

    physical_file = file_obj.physical_file
    if not physical_file or not physical_file.storage_path:
        http_exceptions.raise_internal_error("文件存储路径丢失")

    policy = await Policy.get(session, Policy.id == file_obj.policy_id)
    if not policy:
        http_exceptions.raise_internal_error("存储策略不存在")

    # 读取文件内容
    if policy.type == PolicyType.LOCAL:
        storage_service = LocalStorageService(policy)
        raw_bytes = await storage_service.read_file(physical_file.storage_path)
    elif policy.type == PolicyType.S3:
        s3_service = await S3StorageService.from_policy(policy)
        raw_bytes = await s3_service.download_file(physical_file.storage_path)
    else:
        http_exceptions.raise_internal_error("不支持的存储类型")

    try:
        content = raw_bytes.decode('utf-8')
    except UnicodeDecodeError:
        http_exceptions.raise_bad_request("文件不是有效的 UTF-8 文本")

    # 换行符规范化
    content = content.replace('\r\n', '\n').replace('\r', '\n')
    normalized_bytes = content.encode('utf-8')
    hash_hex = hashlib.sha256(normalized_bytes).hexdigest()

    return TextContentResponse(
        content=content,
        hash=hash_hex,
        size=len(normalized_bytes),
    )


@router.patch(
    path='/content/{file_id}',
    summary='增量保存文本文件',
    description='使用 unified diff 增量更新文本文件内容。',
)
async def patch_file_content(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    file_id: UUID,
    request: PatchContentRequest,
) -> PatchContentResponse:
    """
    增量保存文本文件端点

    接收 unified diff 和 base_hash，验证无并发冲突后应用 patch。

    认证：JWT token 必填

    错误处理：
    - 400: 文件不是有效的 UTF-8 文本
    - 404: 文件不存在
    - 409: base_hash 不匹配（并发冲突）
    - 422: 无效的 patch 格式或 patch 应用失败
    """
    file_obj = await Object.get(
        session,
        (Object.id == file_id) & (Object.deleted_at == None),
        load=Object.physical_file,
    )
    if not file_obj or file_obj.owner_id != user.id:
        http_exceptions.raise_not_found("文件不存在")

    if not file_obj.is_file:
        http_exceptions.raise_bad_request("对象不是文件")

    if file_obj.is_banned:
        http_exceptions.raise_banned()

    physical_file = file_obj.physical_file
    if not physical_file or not physical_file.storage_path:
        http_exceptions.raise_internal_error("文件存储路径丢失")

    storage_path = physical_file.storage_path

    policy = await Policy.get(session, Policy.id == file_obj.policy_id)
    if not policy:
        http_exceptions.raise_internal_error("存储策略不存在")

    # 读取文件内容
    if policy.type == PolicyType.LOCAL:
        storage_service = LocalStorageService(policy)
        raw_bytes = await storage_service.read_file(storage_path)
    elif policy.type == PolicyType.S3:
        s3_service = await S3StorageService.from_policy(policy)
        raw_bytes = await s3_service.download_file(storage_path)
    else:
        http_exceptions.raise_internal_error("不支持的存储类型")

    # 解码 + 规范化
    original_text = raw_bytes.decode('utf-8')
    original_text = original_text.replace('\r\n', '\n').replace('\r', '\n')
    normalized_bytes = original_text.encode('utf-8')

    # 冲突检测（hash 基于规范化后的内容，与 GET 端点一致）
    current_hash = hashlib.sha256(normalized_bytes).hexdigest()
    if current_hash != request.base_hash:
        http_exceptions.raise_conflict("文件内容已被修改，请刷新后重试")

    # 解析并应用 patch
    diffs = list(whatthepatch.parse_patch(request.patch))
    if not diffs:
        http_exceptions.raise_unprocessable_entity("无效的 patch 格式")

    try:
        result = whatthepatch.apply_diff(diffs[0], original_text)
    except HunkApplyException:
        http_exceptions.raise_unprocessable_entity("Patch 应用失败，差异内容与当前文件不匹配")

    new_text = '\n'.join(result)

    # 保持尾部换行符一致
    if original_text.endswith('\n') and not new_text.endswith('\n'):
        new_text += '\n'

    new_bytes = new_text.encode('utf-8')

    # 验证文件大小限制
    _check_policy_size_limit(policy, len(new_bytes))

    # 写入文件
    if policy.type == PolicyType.LOCAL:
        await storage_service.write_file(storage_path, new_bytes)
    elif policy.type == PolicyType.S3:
        await s3_service.upload_file(storage_path, new_bytes)

    # 更新数据库
    owner_id = file_obj.owner_id
    old_size = file_obj.size
    new_size = len(new_bytes)
    size_diff = new_size - old_size

    file_obj.size = new_size
    file_obj = await file_obj.save(session, commit=False)
    physical_file.size = new_size
    physical_file = await physical_file.save(session, commit=False)
    if size_diff != 0:
        await adjust_user_storage(session, owner_id, size_diff, commit=False)
    await session.commit()

    new_hash = hashlib.sha256(new_bytes).hexdigest()

    l.info(f"文本文件增量保存: file_id={file_id}, size={old_size}->{new_size}")

    return PatchContentResponse(new_hash=new_hash, new_size=new_size)


@router.get(
    path='/thumb/{id}',
    summary='获取文件缩略图',
    description='获取文件缩略图。',
    dependencies=[Depends(auth_required)]
)
async def file_thumb(id: str) -> ResponseBase:
    """获取文件缩略图"""
    raise HTTPException(status_code=501, detail="缩略图功能暂未实现")


@router.post(
    path='/source/{file_id}',
    summary='创建/获取文件外链',
    description='为指定文件创建或获取已有的外链地址。',
)
async def file_source(
    session: SessionDep,
    config: ServerConfigDep,
    user: Annotated[User, Depends(auth_required)],
    file_id: UUID,
) -> SourceLinkResponse:
    """
    创建/获取文件外链端点

    检查 policy 是否启用外链，查找或创建 SourceLink，返回外链 URL。

    认证：JWT token 必填

    错误处理：
    - 403: 存储策略未启用外链
    - 404: 文件不存在
    """
    file_obj = await Object.get(
        session,
        (Object.id == file_id) & (Object.deleted_at == None),
    )
    if not file_obj or file_obj.owner_id != user.id:
        http_exceptions.raise_not_found("文件不存在")

    if not file_obj.is_file:
        http_exceptions.raise_bad_request("对象不是文件")

    if file_obj.is_banned:
        http_exceptions.raise_banned()

    policy = await Policy.get(session, Policy.id == file_obj.policy_id)
    if not policy:
        http_exceptions.raise_internal_error("存储策略不存在")

    if not policy.is_origin_link_enable:
        http_exceptions.raise_forbidden("当前存储策略未启用外链功能")

    # 缓存文件名（save 后对象属性会过期）
    file_name = file_obj.name

    # 查找已有 SourceLink
    link: SourceLink | None = await SourceLink.get(
        session,
        (SourceLink.object_id == file_id) & (SourceLink.name == file_name),
    )
    if not link:
        link = SourceLink(
            name=file_name,
            object_id=file_id,
        )
        link = await link.save(session)

    site_url = config.site_url
    url = f"{site_url}/api/v1/file/source/{file_id}/{file_name}"

    return SourceLinkResponse(url=url, downloads=link.downloads)


@router.post(
    path='/archive',
    summary='打包要下载的文件',
    description='将多个文件打包下载。',
    dependencies=[Depends(auth_required)]
)
async def file_archive() -> ResponseBase:
    """打包文件"""
    raise HTTPException(status_code=501, detail="打包功能暂未实现")


@router.post(
    path='/compress',
    summary='创建文件压缩任务',
    description='创建文件压缩任务。',
    dependencies=[Depends(auth_required)]
)
async def file_compress() -> ResponseBase:
    """创建压缩任务"""
    raise HTTPException(status_code=501, detail="压缩功能暂未实现")


@router.post(
    path='/decompress',
    summary='创建文件解压任务',
    description='创建文件解压任务。',
    dependencies=[Depends(auth_required)]
)
async def file_decompress() -> ResponseBase:
    """创建解压任务"""
    raise HTTPException(status_code=501, detail="解压功能暂未实现")


@router.post(
    path='/relocate',
    summary='创建文件转移任务',
    description='创建文件转移任务。',
    dependencies=[Depends(auth_required)]
)
async def file_relocate() -> ResponseBase:
    """创建转移任务"""
    raise HTTPException(status_code=501, detail="转移功能暂未实现")


@router.get(
    path='/search/{type}/{keyword}',
    summary='搜索文件',
    description='按关键字搜索文件。',
    dependencies=[Depends(auth_required)]
)
async def file_search(type: str, keyword: str) -> ResponseBase:
    """搜索文件"""
    raise HTTPException(status_code=501, detail="搜索功能暂未实现")
