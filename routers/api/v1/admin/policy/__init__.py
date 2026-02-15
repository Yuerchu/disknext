from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger as l
from sqlmodel import Field

from middleware.auth import admin_required
from middleware.dependencies import SessionDep, TableViewRequestDep
from sqlmodels import (
    Policy, PolicyBase, PolicyType, PolicySummary, ResponseBase,
    ListResponse, Object,
)
from sqlmodel_ext import SQLModelBase
from service.storage import DirectoryCreationError, LocalStorageService

admin_policy_router = APIRouter(
    prefix='/policy',
    tags=['admin', 'admin_policy']
)


class PathTestResponse(SQLModelBase):
    """路径测试响应"""

    path: str
    """解析后的路径"""

    is_exists: bool
    """路径是否存在"""

    is_writable: bool
    """路径是否可写"""


class PolicyGroupInfo(SQLModelBase):
    """策略关联的用户组信息"""

    id: str
    """用户组UUID"""

    name: str
    """用户组名称"""


class PolicyDetailResponse(SQLModelBase):
    """存储策略详情响应"""

    id: str
    """策略UUID"""

    name: str
    """策略名称"""

    type: str
    """策略类型"""

    server: str | None
    """服务器地址"""

    bucket_name: str | None
    """存储桶名称"""

    is_private: bool
    """是否私有"""

    base_url: str | None
    """基础URL"""

    max_size: int
    """最大文件尺寸"""

    auto_rename: bool
    """是否自动重命名"""

    dir_name_rule: str | None
    """目录命名规则"""

    file_name_rule: str | None
    """文件命名规则"""

    is_origin_link_enable: bool
    """是否启用外链"""

    options: dict[str, Any] | None
    """策略选项"""

    groups: list[PolicyGroupInfo]
    """关联的用户组"""

    object_count: int
    """使用此策略的对象数量"""

class PolicyTestPathRequest(SQLModelBase):
    """测试本地路径请求 DTO"""

    path: str = Field(max_length=512)
    """要测试的本地路径"""


class PolicyTestSlaveRequest(SQLModelBase):
    """测试从机通信请求 DTO"""

    server: str = Field(max_length=255)
    """从机服务器地址"""

    secret: str
    """从机通信密钥"""

class PolicyCreateRequest(PolicyBase):
    """创建存储策略请求 DTO，继承 PolicyBase 中的所有字段"""
    pass

@admin_policy_router.get(
    path='/list',
    summary='列出存储策略',
    description='List all storage policies',
    dependencies=[Depends(admin_required)]
)
async def router_policy_list(
    session: SessionDep,
    table_view: TableViewRequestDep,
) -> ListResponse[PolicySummary]:
    """
    获取所有存储策略列表。

    :param session: 数据库会话
    :param table_view: 分页排序参数依赖
    :return: 分页策略列表
    """
    result = await Policy.get_with_count(session, table_view=table_view)

    return ListResponse(
        items=[PolicySummary.model_validate(p, from_attributes=True) for p in result.items],
        count=result.count,
    )


@admin_policy_router.post(
    path='/test/path',
    summary='测试本地路径可用性',
    description='Test local path availability',
    dependencies=[Depends(admin_required)]
)
async def router_policy_test_path(
    request: PolicyTestPathRequest,
) -> PathTestResponse:
    """
    测试本地存储路径是否可用。

    :param request: 测试请求
    :return: 测试结果
    """
    import aiofiles.os
    from pathlib import Path

    path = Path(request.path).resolve()

    # 检查路径是否存在
    is_exists = await aiofiles.os.path.exists(str(path))

    # 检查是否可写
    is_writable = False
    if is_exists:
        test_file = path / ".write_test"
        try:
            async with aiofiles.open(str(test_file), 'w') as f:
                await f.write("test")
            await aiofiles.os.remove(str(test_file))
            is_writable = True
        except Exception:
            pass

    return PathTestResponse(
        path=str(path),
        is_exists=is_exists,
        is_writable=is_writable,
    )


@admin_policy_router.post(
    path='/test/slave',
    summary='测试从机通信',
    description='Test slave node communication',
    dependencies=[Depends(admin_required)],
    status_code=204,
)
async def router_policy_test_slave(
    request: PolicyTestSlaveRequest,
) -> None:
    """
    测试从机RPC通信。

    :param request: 测试请求
    :return: 测试结果
    """
    import aiohttp

    try:
        async with aiohttp.ClientSession() as client:
            async with client.get(
                f"{request.server}/api/slave/ping",
                headers={"Authorization": request.secret},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    return
                else:
                    raise HTTPException(
                        status_code=400,
                        detail=f"从机响应错误，HTTP {resp.status}",
                    )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"连接失败: {str(e)}")

@admin_policy_router.post(
    path='/',
    summary='创建存储策略',
    description='创建新的存储策略。对于本地存储策略，会自动创建物理目录。',
    dependencies=[Depends(admin_required)],
    status_code=204,
)
async def router_policy_add_policy(
    session: SessionDep,
    request: PolicyCreateRequest,
) -> None:
    """
    创建存储策略端点

    功能：
    - 创建新的存储策略配置
    - 对于 LOCAL 类型，自动创建物理目录

    认证：
    - 需要管理员权限

    :param session: 数据库会话
    :param request: 创建请求
    :return: 创建结果
    """
    # 验证本地存储策略必须指定 server 路径
    if request.type == PolicyType.LOCAL:
        if not request.server:
            raise HTTPException(status_code=400, detail="本地存储策略必须指定 server 路径")

    # 检查策略名称是否已存在
    existing = await Policy.get(session, Policy.name == request.name)
    if existing:
        raise HTTPException(status_code=409, detail="策略名称已存在")

    # 创建策略对象
    policy = Policy(
        name=request.name,
        type=request.type,
        server=request.server,
        bucket_name=request.bucket_name,
        is_private=request.is_private,
        base_url=request.base_url,
        access_key=request.access_key,
        secret_key=request.secret_key,
        max_size=request.max_size,
        auto_rename=request.auto_rename,
        dir_name_rule=request.dir_name_rule,
        file_name_rule=request.file_name_rule,
        is_origin_link_enable=request.is_origin_link_enable,
    )

    # 对于本地存储策略，创建物理目录
    if policy.type == PolicyType.LOCAL:
        try:
            storage_service = LocalStorageService(policy)
            await storage_service.ensure_base_directory()
            l.info(f"已为本地存储策略 '{policy.name}' 创建目录: {policy.server}")
        except DirectoryCreationError as e:
            raise HTTPException(status_code=500, detail=f"创建存储目录失败: {e}")

    # 保存到数据库
    await policy.save(session)

@admin_policy_router.post(
    path='/cors',
    summary='创建跨域策略',
    description='Create CORS policy for S3 storage',
    dependencies=[Depends(admin_required)]
)
async def router_policy_add_cors() -> ResponseBase:
    """
    创建CORS配置（S3相关）。

    此端点用于S3存储的跨域配置。
    """
    # TODO: 实现S3 CORS配置
    raise HTTPException(status_code=501, detail="S3 CORS配置暂未实现")


@admin_policy_router.post(
    path='/scf',
    summary='创建COS回调函数',
    description='Create COS callback function',
    dependencies=[Depends(admin_required)]
)
async def router_policy_add_scf() -> ResponseBase:
    """
    创建COS回调函数。

    此端点用于腾讯云COS的云函数回调配置。
    """
    # TODO: 实现COS SCF配置
    raise HTTPException(status_code=501, detail="COS回调函数配置暂未实现")


@admin_policy_router.get(
    path='/{policy_id}/oauth',
    summary='获取 OneDrive OAuth URL',
    description='Get OneDrive OAuth URL',
    dependencies=[Depends(admin_required)]
)
async def router_policy_onddrive_oauth(
    session: SessionDep,
    policy_id: UUID,
) -> ResponseBase:
    """
    获取OneDrive OAuth授权URL。

    :param session: 数据库会话
    :param policy_id: 存储策略UUID
    :return: OAuth URL
    """
    policy = await Policy.get(session, Policy.id == policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="存储策略不存在")

    # TODO: 实现OneDrive OAuth
    raise HTTPException(status_code=501, detail="OneDrive OAuth暂未实现")


@admin_policy_router.get(
    path='/{policy_id}',
    summary='获取存储策略',
    description='Get storage policy by ID',
    dependencies=[Depends(admin_required)]
)
async def router_policy_get_policy(
    session: SessionDep,
    policy_id: UUID,
) -> PolicyDetailResponse:
    """
    获取存储策略详情。

    :param session: 数据库会话
    :param policy_id: 存储策略UUID
    :return: 策略详情
    """
    policy = await Policy.get(session, Policy.id == policy_id, load=Policy.options)
    if not policy:
        raise HTTPException(status_code=404, detail="存储策略不存在")

    # 获取使用此策略的用户组
    groups = await policy.awaitable_attrs.groups

    # 统计使用此策略的对象数量
    object_count = await Object.count(session, Object.policy_id == policy_id)

    return PolicyDetailResponse(
        id=str(policy.id),
        name=policy.name,
        type=policy.type.value,
        server=policy.server,
        bucket_name=policy.bucket_name,
        is_private=policy.is_private,
        base_url=policy.base_url,
        max_size=policy.max_size,
        auto_rename=policy.auto_rename,
        dir_name_rule=policy.dir_name_rule,
        file_name_rule=policy.file_name_rule,
        is_origin_link_enable=policy.is_origin_link_enable,
        options=policy.options.model_dump() if policy.options else None,
        groups=[PolicyGroupInfo(id=str(g.id), name=g.name) for g in groups],
        object_count=object_count,
    )


@admin_policy_router.delete(
    path='/{policy_id}',
    summary='删除存储策略',
    description='Delete storage policy by ID',
    dependencies=[Depends(admin_required)],
    status_code=204,
)
async def router_policy_delete_policy(
    session: SessionDep,
    policy_id: UUID,
) -> None:
    """
    删除存储策略。

    注意: 如果有文件使用此策略，会拒绝删除。

    :param session: 数据库会话
    :param policy_id: 存储策略UUID
    :return: 删除结果
    """
    policy = await Policy.get(session, Policy.id == policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="存储策略不存在")

    # 检查是否有文件使用此策略
    file_count = await Object.count(session, Object.policy_id == policy_id)
    if file_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"无法删除，还有 {file_count} 个文件使用此策略"
        )

    policy_name = policy.name
    await Policy.delete(session, policy)

    l.info(f"管理员删除了存储策略: {policy_name}")