"""
管理员 SMS 提供商端点集成测试

测试短信宝和腾讯云短信提供商的 CRUD 端点。
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodels.sms import SMSBaoProvider, TencentCloudSMSProvider


# ==================== Fixtures ====================

@pytest_asyncio.fixture
async def smsbao_provider(initialized_db: AsyncSession) -> SMSBaoProvider:
    """创建测试用短信宝提供商"""
    provider = SMSBaoProvider(
        name="测试短信宝",
        enabled=True,
        username="testuser",
        password="md5hashvalue",
        template="您的验证码是{code}，有效期{time}分钟。",
    )
    provider = await provider.save(initialized_db)
    return provider


@pytest_asyncio.fixture
async def tencent_provider(initialized_db: AsyncSession) -> TencentCloudSMSProvider:
    """创建测试用腾讯云短信提供商"""
    provider = TencentCloudSMSProvider(
        name="测试腾讯云",
        enabled=True,
        secret_id="AKIDxxxxxxxx",
        secret_key="secretxxxxxxxx",
        sms_sdk_app_id="1400000001",
        sign_name="测试签名",
        template_id="100001",
    )
    provider = await provider.save(initialized_db)
    return provider


# ==================== 短信宝 CRUD 测试 ====================

class TestSMSBaoProviderCRUD:
    """短信宝提供商 CRUD 端点测试"""

    @pytest.mark.asyncio
    async def test_create_smsbao_provider(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        initialized_db: AsyncSession,
    ) -> None:
        """创建短信宝提供商"""
        response = await async_client.post(
            "/api/v1/admin/sms/smsbao",
            headers=admin_headers,
            json={
                "name": "新建短信宝",
                "enabled": True,
                "username": "newuser",
                "password": "newpassmd5",
                "template": "验证码{code}，{time}分钟有效",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "新建短信宝"
        assert data["username"] == "newuser"
        assert "password" not in data  # 响应不包含密码

    @pytest.mark.asyncio
    async def test_create_duplicate_name(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        smsbao_provider: SMSBaoProvider,
    ) -> None:
        """重复名称返回 409"""
        response = await async_client.post(
            "/api/v1/admin/sms/smsbao",
            headers=admin_headers,
            json={
                "name": smsbao_provider.name,
                "username": "x",
                "password": "y",
                "template": "z",
            },
        )
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_list_smsbao_providers(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        smsbao_provider: SMSBaoProvider,
    ) -> None:
        """列出短信宝提供商"""
        response = await async_client.get(
            "/api/v1/admin/sms/smsbao",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any(p["name"] == smsbao_provider.name for p in data)

    @pytest.mark.asyncio
    async def test_get_smsbao_provider(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        smsbao_provider: SMSBaoProvider,
    ) -> None:
        """获取短信宝提供商详情"""
        response = await async_client.get(
            f"/api/v1/admin/sms/smsbao/{smsbao_provider.id}",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == smsbao_provider.name

    @pytest.mark.asyncio
    async def test_get_nonexistent_provider(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
    ) -> None:
        """获取不存在的提供商返回 404"""
        from uuid import uuid4
        response = await async_client.get(
            f"/api/v1/admin/sms/smsbao/{uuid4()}",
            headers=admin_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_smsbao_provider(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        smsbao_provider: SMSBaoProvider,
    ) -> None:
        """更新短信宝提供商"""
        response = await async_client.patch(
            f"/api/v1/admin/sms/smsbao/{smsbao_provider.id}",
            headers=admin_headers,
            json={"name": "更新后的名称"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "更新后的名称"

    @pytest.mark.asyncio
    async def test_delete_smsbao_provider(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        smsbao_provider: SMSBaoProvider,
    ) -> None:
        """删除短信宝提供商"""
        response = await async_client.delete(
            f"/api/v1/admin/sms/smsbao/{smsbao_provider.id}",
            headers=admin_headers,
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_non_admin_forbidden(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """非管理员访问返回 403"""
        response = await async_client.get(
            "/api/v1/admin/sms/smsbao",
            headers=auth_headers,
        )
        assert response.status_code == 403


# ==================== 腾讯云短信 CRUD 测试 ====================

class TestTencentSMSProviderCRUD:
    """腾讯云短信提供商 CRUD 端点测试"""

    @pytest.mark.asyncio
    async def test_create_tencent_provider(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        initialized_db: AsyncSession,
    ) -> None:
        """创建腾讯云短信提供商"""
        response = await async_client.post(
            "/api/v1/admin/sms/tencent",
            headers=admin_headers,
            json={
                "name": "新建腾讯云",
                "secret_id": "AKID_test",
                "secret_key": "secret_test",
                "sms_sdk_app_id": "1400000002",
                "sign_name": "测试签名",
                "template_id": "100002",
                "region": "ap-guangzhou",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "新建腾讯云"
        assert data["sms_sdk_app_id"] == "1400000002"

    @pytest.mark.asyncio
    async def test_list_tencent_providers(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        tencent_provider: TencentCloudSMSProvider,
    ) -> None:
        """列出腾讯云短信提供商"""
        response = await async_client.get(
            "/api/v1/admin/sms/tencent",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_get_tencent_provider(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        tencent_provider: TencentCloudSMSProvider,
    ) -> None:
        """获取腾讯云短信提供商详情"""
        response = await async_client.get(
            f"/api/v1/admin/sms/tencent/{tencent_provider.id}",
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["name"] == tencent_provider.name

    @pytest.mark.asyncio
    async def test_update_tencent_provider(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        tencent_provider: TencentCloudSMSProvider,
    ) -> None:
        """更新腾讯云短信提供商"""
        response = await async_client.patch(
            f"/api/v1/admin/sms/tencent/{tencent_provider.id}",
            headers=admin_headers,
            json={"sign_name": "新签名"},
        )
        assert response.status_code == 200
        assert response.json()["sign_name"] == "新签名"

    @pytest.mark.asyncio
    async def test_delete_tencent_provider(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        tencent_provider: TencentCloudSMSProvider,
    ) -> None:
        """删除腾讯云短信提供商"""
        response = await async_client.delete(
            f"/api/v1/admin/sms/tencent/{tencent_provider.id}",
            headers=admin_headers,
        )
        assert response.status_code == 204
