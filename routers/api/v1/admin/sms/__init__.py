"""
管理员短信提供商管理端点

提供短信宝和腾讯云短信提供商的增删改查。
"""
from uuid import UUID

from fastapi import APIRouter, Depends, status
from loguru import logger as l
from sqlmodel_ext import cond

from middleware.dependencies import SessionDep
from middleware.scope import require_scope
from sqlmodels.sms import (
    SmsProvider,
    SMSBaoProvider,
    SMSBaoProviderCreateRequest,
    SMSBaoProviderUpdateRequest,
    SMSBaoProviderInfoResponse,
    TencentCloudSMSProvider,
    TencentCloudSMSProviderCreateRequest,
    TencentCloudSMSProviderUpdateRequest,
    TencentCloudSMSProviderInfoResponse,
)
from utils import http_exceptions
from utils.http.error_codes import ErrorCode as E

admin_sms_router = APIRouter(
    prefix="/sms",
    tags=["admin", "admin_sms"],
    dependencies=[Depends(require_scope("admin.settings:read:all"))],
)


# ==================== 短信宝 ====================

@admin_sms_router.post(
    path='/smsbao',
    summary='创建短信宝提供商',
    dependencies=[Depends(require_scope("admin.settings:write:all"))],
    status_code=status.HTTP_201_CREATED,
)
async def create_smsbao_provider(
    session: SessionDep,
    request: SMSBaoProviderCreateRequest,
) -> SMSBaoProviderInfoResponse:
    """创建短信宝提供商配置"""
    existing = await SMSBaoProvider.get(session, cond(SMSBaoProvider.name == request.name))
    if existing:
        http_exceptions.raise_conflict(E.SMS_PROVIDER_NAME_EXISTS, "提供商名称已存在")

    provider = SMSBaoProvider(
        name=request.name,
        enabled=request.enabled,
        username=request.username,
        password=request.password,
        template=request.template,
    )
    provider = await provider.save(session)
    l.info(f"创建短信宝提供商: {provider.name}")
    return SMSBaoProviderInfoResponse.model_validate(provider, from_attributes=True)


@admin_sms_router.get(
    path='/smsbao',
    summary='列出短信宝提供商',
)
async def list_smsbao_providers(
    session: SessionDep,
) -> list[SMSBaoProviderInfoResponse]:
    """列出所有短信宝提供商配置"""
    providers: list[SMSBaoProvider] = await SMSBaoProvider.get(session, fetch_mode="all")
    return [
        SMSBaoProviderInfoResponse.model_validate(p, from_attributes=True)
        for p in providers
    ]


@admin_sms_router.get(
    path='/smsbao/{provider_id}',
    summary='获取短信宝提供商详情',
)
async def get_smsbao_provider(
    session: SessionDep,
    provider_id: UUID,
) -> SMSBaoProviderInfoResponse:
    """获取短信宝提供商详情"""
    provider: SMSBaoProvider | None = await SMSBaoProvider.get(
        session, cond(SMSBaoProvider.id == provider_id),
    )
    if not provider:
        http_exceptions.raise_not_found(E.SMS_PROVIDER_NOT_FOUND, "提供商不存在")
    return SMSBaoProviderInfoResponse.model_validate(provider, from_attributes=True)


@admin_sms_router.patch(
    path='/smsbao/{provider_id}',
    summary='更新短信宝提供商',
    dependencies=[Depends(require_scope("admin.settings:write:all"))],
)
async def update_smsbao_provider(
    session: SessionDep,
    provider_id: UUID,
    request: SMSBaoProviderUpdateRequest,
) -> SMSBaoProviderInfoResponse:
    """更新短信宝提供商配置"""
    provider: SMSBaoProvider | None = await SMSBaoProvider.get(
        session, cond(SMSBaoProvider.id == provider_id),
    )
    if not provider:
        http_exceptions.raise_not_found(E.SMS_PROVIDER_NOT_FOUND, "提供商不存在")
    provider = await provider.update(session, request)
    l.info(f"更新短信宝提供商: {provider.name}")
    return SMSBaoProviderInfoResponse.model_validate(provider, from_attributes=True)


@admin_sms_router.delete(
    path='/smsbao/{provider_id}',
    summary='删除短信宝提供商',
    dependencies=[Depends(require_scope("admin.settings:write:all"))],
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_smsbao_provider(
    session: SessionDep,
    provider_id: UUID,
) -> None:
    """删除短信宝提供商"""
    provider: SMSBaoProvider | None = await SMSBaoProvider.get(
        session, cond(SMSBaoProvider.id == provider_id),
    )
    if not provider:
        http_exceptions.raise_not_found(E.SMS_PROVIDER_NOT_FOUND, "提供商不存在")
    await SMSBaoProvider.delete(session, provider)
    l.info(f"删除短信宝提供商: {provider.name}")


# ==================== 腾讯云短信 ====================

@admin_sms_router.post(
    path='/tencent',
    summary='创建腾讯云短信提供商',
    dependencies=[Depends(require_scope("admin.settings:write:all"))],
    status_code=status.HTTP_201_CREATED,
)
async def create_tencent_provider(
    session: SessionDep,
    request: TencentCloudSMSProviderCreateRequest,
) -> TencentCloudSMSProviderInfoResponse:
    """创建腾讯云短信提供商配置"""
    existing = await TencentCloudSMSProvider.get(
        session, cond(TencentCloudSMSProvider.name == request.name),
    )
    if existing:
        http_exceptions.raise_conflict(E.SMS_PROVIDER_NAME_EXISTS, "提供商名称已存在")

    provider = TencentCloudSMSProvider(
        name=request.name,
        enabled=request.enabled,
        secret_id=request.secret_id,
        secret_key=request.secret_key,
        sms_sdk_app_id=request.sms_sdk_app_id,
        sign_name=request.sign_name,
        template_id=request.template_id,
        region=request.region,
    )
    provider = await provider.save(session)
    l.info(f"创建腾讯云短信提供商: {provider.name}")
    return TencentCloudSMSProviderInfoResponse.model_validate(provider, from_attributes=True)


@admin_sms_router.get(
    path='/tencent',
    summary='列出腾讯云短信提供商',
)
async def list_tencent_providers(
    session: SessionDep,
) -> list[TencentCloudSMSProviderInfoResponse]:
    """列出所有腾讯云短信提供商配置"""
    providers: list[TencentCloudSMSProvider] = await TencentCloudSMSProvider.get(
        session, fetch_mode="all",
    )
    return [
        TencentCloudSMSProviderInfoResponse.model_validate(p, from_attributes=True)
        for p in providers
    ]


@admin_sms_router.get(
    path='/tencent/{provider_id}',
    summary='获取腾讯云短信提供商详情',
)
async def get_tencent_provider(
    session: SessionDep,
    provider_id: UUID,
) -> TencentCloudSMSProviderInfoResponse:
    """获取腾讯云短信提供商详情"""
    provider: TencentCloudSMSProvider | None = await TencentCloudSMSProvider.get(
        session, cond(TencentCloudSMSProvider.id == provider_id),
    )
    if not provider:
        http_exceptions.raise_not_found(E.SMS_PROVIDER_NOT_FOUND, "提供商不存在")
    return TencentCloudSMSProviderInfoResponse.model_validate(provider, from_attributes=True)


@admin_sms_router.patch(
    path='/tencent/{provider_id}',
    summary='更新腾讯云短信提供商',
    dependencies=[Depends(require_scope("admin.settings:write:all"))],
)
async def update_tencent_provider(
    session: SessionDep,
    provider_id: UUID,
    request: TencentCloudSMSProviderUpdateRequest,
) -> TencentCloudSMSProviderInfoResponse:
    """更新腾讯云短信提供商配置"""
    provider: TencentCloudSMSProvider | None = await TencentCloudSMSProvider.get(
        session, cond(TencentCloudSMSProvider.id == provider_id),
    )
    if not provider:
        http_exceptions.raise_not_found(E.SMS_PROVIDER_NOT_FOUND, "提供商不存在")
    provider = await provider.update(session, request)
    l.info(f"更新腾讯云短信提供商: {provider.name}")
    return TencentCloudSMSProviderInfoResponse.model_validate(provider, from_attributes=True)


@admin_sms_router.delete(
    path='/tencent/{provider_id}',
    summary='删除腾讯云短信提供商',
    dependencies=[Depends(require_scope("admin.settings:write:all"))],
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_tencent_provider(
    session: SessionDep,
    provider_id: UUID,
) -> None:
    """删除腾讯云短信提供商"""
    provider: TencentCloudSMSProvider | None = await TencentCloudSMSProvider.get(
        session, cond(TencentCloudSMSProvider.id == provider_id),
    )
    if not provider:
        http_exceptions.raise_not_found(E.SMS_PROVIDER_NOT_FOUND, "提供商不存在")
    await TencentCloudSMSProvider.delete(session, provider)
    l.info(f"删除腾讯云短信提供商: {provider.name}")
