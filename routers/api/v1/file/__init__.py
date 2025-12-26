"""
文件操作路由

提供文件上传、下载、创建等核心功能。

路由结构：
- /file - 文件操作
- /file/upload - 上传相关操作
- /file/download - 下载相关操作
"""
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from loguru import logger as l

from middleware.auth import auth_required
from middleware.dependencies import SessionDep
from models import (
    CreateFileRequest,
    CreateUploadSessionRequest,
    Object,
    ObjectType,
    PhysicalFile,
    Policy,
    PolicyType,
    ResponseBase,
    UploadChunkResponse,
    UploadSession,
    UploadSessionResponse,
    User,
)
from service.storage import LocalStorageService
from utils.JWT import SECRET_KEY
from utils import http_exceptions


# ==================== 下载令牌管理 ====================

class DownloadTokenManager:
    """下载令牌管理器（JWT 无状态）"""

    _ttl: timedelta = timedelta(hours=1)

    @classmethod
    def create(cls, file_id: UUID, owner_id: int) -> str:
        """创建下载令牌"""
        payload = {
            "file_id": str(file_id),
            "owner_id": owner_id,
            "exp": datetime.now(timezone.utc) + cls._ttl,
            "type": "download",
        }
        return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

    @classmethod
    def verify(cls, token: str) -> tuple[UUID, int] | None:
        """
        验证令牌并返回 (file_id, owner_id)

        :return: (file_id, owner_id) 或 None（验证失败）
        """
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            if payload.get("type") != "download":
                return None
            return UUID(payload["file_id"]), payload["owner_id"]
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return None


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

    # 验证父目录
    parent = await Object.get(session, Object.id == request.parent_id)
    if not parent or parent.owner_id != user.id:
        raise HTTPException(status_code=404, detail="父目录不存在")

    if not parent.is_folder:
        raise HTTPException(status_code=400, detail="父对象不是目录")

    # 确定存储策略
    policy_id = request.policy_id or parent.policy_id
    policy = await Policy.get(session, Policy.id == policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="存储策略不存在")

    # 验证文件大小限制
    if policy.max_size > 0 and request.file_size > policy.max_size:
        raise HTTPException(
            status_code=400,
            detail=f"文件大小超过限制 ({policy.max_size} bytes)"
        )

    # 检查是否已存在同名文件
    existing = await Object.get(
        session,
        (Object.owner_id == user.id) &
        (Object.parent_id == parent.id) &
        (Object.name == request.file_name)
    )
    if existing:
        raise HTTPException(status_code=409, detail="同名文件已存在")

    # 计算分片信息
    options = await policy.awaitable_attrs.options
    chunk_size = options.chunk_size if options else 52428800  # 默认 50MB
    total_chunks = max(1, (request.file_size + chunk_size - 1) // chunk_size) if request.file_size > 0 else 1

    # 生成存储路径
    storage_path: str | None = None
    if policy.type == PolicyType.LOCAL:
        storage_service = LocalStorageService(policy)
        dir_path, storage_name, full_path = await storage_service.generate_file_path(
            user_id=user.id,
            original_filename=request.file_name,
        )
        storage_path = full_path
    else:
        raise HTTPException(status_code=501, detail="S3 存储暂未实现")

    # 创建上传会话
    upload_session = UploadSession(
        file_name=request.file_name,
        file_size=request.file_size,
        chunk_size=chunk_size,
        total_chunks=total_chunks,
        storage_path=storage_path,
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
    else:
        raise HTTPException(status_code=501, detail="S3 存储暂未实现")

    # 更新会话进度
    upload_session.uploaded_chunks += 1
    upload_session.uploaded_size += len(content)
    upload_session = await upload_session.save(session)

    # 检查是否完成
    is_complete = upload_session.is_complete
    file_object_id: UUID | None = None

    if is_complete:
        # 创建 PhysicalFile 记录
        physical_file = PhysicalFile(
            storage_path=upload_session.storage_path,
            size=upload_session.uploaded_size,
            policy_id=upload_session.policy_id,
            reference_count=1,
        )
        physical_file = await physical_file.save(session)

        # 创建 Object 记录
        file_object = Object(
            name=upload_session.file_name,
            type=ObjectType.FILE,
            size=upload_session.uploaded_size,
            physical_file_id=physical_file.id,
            upload_session_id=str(upload_session.id),
            parent_id=upload_session.parent_id,
            owner_id=user_id,
            policy_id=upload_session.policy_id,
        )
        file_object = await file_object.save(session)
        file_object_id = file_object.id

        # 删除上传会话
        await UploadSession.delete(session, upload_session)

        l.info(f"文件上传完成: {file_object.name}, size={file_object.size}, id={file_object.id}")

    return UploadChunkResponse(
        uploaded_chunks=upload_session.uploaded_chunks if not is_complete else upload_session.total_chunks,
        total_chunks=upload_session.total_chunks,
        is_complete=is_complete,
        object_id=file_object_id,
    )


@_upload_router.delete(
    path='/{session_id}',
    summary='删除上传会话',
    description='取消上传并删除会话及已上传的临时文件。',
)
async def delete_upload_session(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    session_id: UUID,
) -> ResponseBase:
    """删除上传会话端点"""
    upload_session = await UploadSession.get(session, UploadSession.id == session_id)
    if not upload_session or upload_session.owner_id != user.id:
        raise HTTPException(status_code=404, detail="上传会话不存在")

    # 删除临时文件
    policy = await Policy.get(session, Policy.id == upload_session.policy_id)
    if policy and policy.type == PolicyType.LOCAL and upload_session.storage_path:
        storage_service = LocalStorageService(policy)
        await storage_service.delete_file(upload_session.storage_path)

    # 删除会话记录
    await UploadSession.delete(session, upload_session)

    l.info(f"删除上传会话: {session_id}")

    return ResponseBase(data={"deleted": True})


@_upload_router.delete(
    path='/',
    summary='清除所有上传会话',
    description='清除当前用户的所有上传会话。',
)
async def clear_upload_sessions(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
) -> ResponseBase:
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
        if policy and policy.type == PolicyType.LOCAL and upload_session.storage_path:
            storage_service = LocalStorageService(policy)
            await storage_service.delete_file(upload_session.storage_path)

        await UploadSession.delete(session, upload_session)
        deleted_count += 1

    l.info(f"清除用户 {user.id} 的所有上传会话，共 {deleted_count} 个")

    return ResponseBase(data={"deleted": deleted_count})


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
async def create_download_token(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    file_id: UUID,
) -> ResponseBase:
    """
    创建下载令牌端点

    验证文件存在且属于当前用户后，生成 JWT 下载令牌。
    """
    file_obj = await Object.get(session, Object.id == file_id)
    if not file_obj or file_obj.owner_id != user.id:
        raise HTTPException(status_code=404, detail="文件不存在")

    if not file_obj.is_file:
        raise HTTPException(status_code=400, detail="对象不是文件")

    token = DownloadTokenManager.create(file_id, user.id)

    l.debug(f"创建下载令牌: file_id={file_id}, user_id={user.id}")

    return ResponseBase(data={"token": token, "expires_in": 3600})


@_download_router.get(
    path='/{token}',
    summary='下载文件',
    description='使用下载令牌下载文件。',
)
async def download_file(
    session: SessionDep,
    token: str,
) -> FileResponse:
    """
    下载文件端点

    验证 JWT 令牌后返回文件内容。
    """
    # 验证令牌
    result = DownloadTokenManager.verify(token)
    if not result:
        raise HTTPException(status_code=401, detail="下载令牌无效或已过期")

    file_id, owner_id = result

    # 获取文件对象
    file_obj = await Object.get(session, Object.id == file_id)
    if not file_obj or file_obj.owner_id != owner_id:
        raise HTTPException(status_code=404, detail="文件不存在")

    if not file_obj.is_file:
        raise HTTPException(status_code=400, detail="对象不是文件")

    if not file_obj.source_name:
        raise HTTPException(status_code=500, detail="文件存储路径丢失")

    # 获取策略
    policy = await Policy.get(session, Policy.id == file_obj.policy_id)
    if not policy:
        raise HTTPException(status_code=500, detail="存储策略不存在")

    if policy.type == PolicyType.LOCAL:
        storage_service = LocalStorageService(policy)
        if not await storage_service.file_exists(file_obj.source_name):
            raise HTTPException(status_code=404, detail="物理文件不存在")

        return FileResponse(
            path=file_obj.source_name,
            filename=file_obj.name,
            media_type="application/octet-stream",
        )
    else:
        raise HTTPException(status_code=501, detail="S3 存储暂未实现")


# ==================== 包含子路由 ====================

router.include_router(_upload_router)
router.include_router(_download_router)


# ==================== 创建空白文件 ====================

@router.post(
    path='/create',
    summary='创建空白文件',
    description='在指定目录下创建空白文件。',
)
async def create_empty_file(
    session: SessionDep,
    user: Annotated[User, Depends(auth_required)],
    request: CreateFileRequest,
) -> ResponseBase:
    """创建空白文件端点"""
    # 存储 user.id，避免后续 save() 导致 user 过期后无法访问
    user_id = user.id

    # 验证文件名
    if not request.name or '/' in request.name or '\\' in request.name:
        raise HTTPException(status_code=400, detail="无效的文件名")

    # 验证父目录
    parent = await Object.get(session, Object.id == request.parent_id)
    if not parent or parent.owner_id != user_id:
        raise HTTPException(status_code=404, detail="父目录不存在")

    if not parent.is_folder:
        raise HTTPException(status_code=400, detail="父对象不是目录")

    # 检查是否已存在同名文件
    existing = await Object.get(
        session,
        (Object.owner_id == user_id) &
        (Object.parent_id == parent.id) &
        (Object.name == request.name)
    )
    if existing:
        raise HTTPException(status_code=409, detail="同名文件已存在")

    # 确定存储策略
    policy_id = request.policy_id or parent.policy_id
    policy = await Policy.get(session, Policy.id == policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="存储策略不存在")

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
    else:
        raise HTTPException(status_code=501, detail="S3 存储暂未实现")

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

    return ResponseBase(data={
        "id": str(file_object.id),
        "name": file_object.name,
        "size": file_object.size,
    })


# ==================== 文件外链（保留原有端点结构） ====================

@router.get(
    path='/get/{id}/{name}',
    summary='文件外链（直接输出文件数据）',
    description='通过外链直接获取文件内容。',
)
async def file_get(
    session: SessionDep,
    id: str,
    name: str,
) -> FileResponse:
    """文件外链端点（直接输出）"""
    raise HTTPException(status_code=501, detail="外链功能暂未实现")


@router.get(
    path='/source/{id}/{name}',
    summary='文件外链(301跳转)',
    description='通过外链获取文件重定向地址。',
)
async def file_source_redirect(id: str, name: str) -> ResponseBase:
    """文件外链端点（301跳转）"""
    raise HTTPException(status_code=501, detail="外链功能暂未实现")


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
    path='/preview/{id}',
    summary='预览文件',
    description='获取文件预览。',
    dependencies=[Depends(auth_required)]
)
async def file_preview(id: str) -> ResponseBase:
    """预览文件"""
    raise HTTPException(status_code=501, detail="预览功能暂未实现")


@router.get(
    path='/content/{id}',
    summary='获取文本文件内容',
    description='获取文本文件内容。',
    dependencies=[Depends(auth_required)]
)
async def file_content(id: str) -> ResponseBase:
    """获取文本文件内容"""
    raise HTTPException(status_code=501, detail="文本内容功能暂未实现")


@router.get(
    path='/doc/{id}',
    summary='获取Office文档预览地址',
    description='获取Office文档在线预览地址。',
    dependencies=[Depends(auth_required)]
)
async def file_doc(id: str) -> ResponseBase:
    """获取Office文档预览地址"""
    raise HTTPException(status_code=501, detail="Office预览功能暂未实现")


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
    path='/source/{id}',
    summary='取得文件外链',
    description='获取文件的外链地址。',
    dependencies=[Depends(auth_required)]
)
async def file_source(id: str) -> ResponseBase:
    """获取文件外链"""
    raise HTTPException(status_code=501, detail="外链功能暂未实现")


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
