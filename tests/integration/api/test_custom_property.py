"""
自定义属性定义端点集成测试
"""
import pytest
from httpx import AsyncClient
from uuid import UUID, uuid4


# ==================== 获取属性定义列表测试 ====================

@pytest.mark.asyncio
async def test_list_custom_properties_requires_auth(async_client: AsyncClient):
    """测试获取属性定义需要认证"""
    response = await async_client.get("/api/v1/object/custom_property")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_custom_properties_empty(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """测试获取空的属性定义列表"""
    response = await async_client.get(
        "/api/v1/object/custom_property",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data == []


# ==================== 创建属性定义测试 ====================

@pytest.mark.asyncio
async def test_create_custom_property(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """测试创建自定义属性"""
    response = await async_client.post(
        "/api/v1/object/custom_property",
        headers=auth_headers,
        json={
            "name": "评分",
            "type": "rating",
            "icon": "mdi:star",
        },
    )
    assert response.status_code == 204

    # 验证已创建
    list_response = await async_client.get(
        "/api/v1/object/custom_property",
        headers=auth_headers,
    )
    data = list_response.json()
    assert len(data) == 1
    assert data[0]["name"] == "评分"
    assert data[0]["type"] == "rating"
    assert data[0]["icon"] == "mdi:star"


@pytest.mark.asyncio
async def test_create_custom_property_with_options(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """测试创建带选项的自定义属性"""
    response = await async_client.post(
        "/api/v1/object/custom_property",
        headers=auth_headers,
        json={
            "name": "分类",
            "type": "select",
            "options": ["工作", "个人", "归档"],
            "default_value": "个人",
        },
    )
    assert response.status_code == 204

    list_response = await async_client.get(
        "/api/v1/object/custom_property",
        headers=auth_headers,
    )
    data = list_response.json()
    prop = next(p for p in data if p["name"] == "分类")
    assert prop["type"] == "select"
    assert prop["options"] == ["工作", "个人", "归档"]
    assert prop["default_value"] == "个人"


@pytest.mark.asyncio
async def test_create_custom_property_duplicate_name(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """测试创建同名属性返回 409"""
    # 先创建
    await async_client.post(
        "/api/v1/object/custom_property",
        headers=auth_headers,
        json={"name": "标签", "type": "text"},
    )

    # 再创建同名
    response = await async_client.post(
        "/api/v1/object/custom_property",
        headers=auth_headers,
        json={"name": "标签", "type": "text"},
    )
    assert response.status_code == 409


# ==================== 更新属性定义测试 ====================

@pytest.mark.asyncio
async def test_update_custom_property(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """测试更新自定义属性"""
    # 先创建
    await async_client.post(
        "/api/v1/object/custom_property",
        headers=auth_headers,
        json={"name": "备注", "type": "text"},
    )

    # 获取 ID
    list_response = await async_client.get(
        "/api/v1/object/custom_property",
        headers=auth_headers,
    )
    prop_id = next(p["id"] for p in list_response.json() if p["name"] == "备注")

    # 更新
    response = await async_client.patch(
        f"/api/v1/object/custom_property/{prop_id}",
        headers=auth_headers,
        json={"name": "详细备注", "icon": "mdi:note"},
    )
    assert response.status_code == 204

    # 验证已更新
    list_response = await async_client.get(
        "/api/v1/object/custom_property",
        headers=auth_headers,
    )
    prop = next(p for p in list_response.json() if p["id"] == prop_id)
    assert prop["name"] == "详细备注"
    assert prop["icon"] == "mdi:note"


@pytest.mark.asyncio
async def test_update_custom_property_not_found(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """测试更新不存在的属性返回 404"""
    fake_id = str(uuid4())
    response = await async_client.patch(
        f"/api/v1/object/custom_property/{fake_id}",
        headers=auth_headers,
        json={"name": "不存在"},
    )
    assert response.status_code == 404


# ==================== 删除属性定义测试 ====================

@pytest.mark.asyncio
async def test_delete_custom_property(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """测试删除自定义属性"""
    # 先创建
    await async_client.post(
        "/api/v1/object/custom_property",
        headers=auth_headers,
        json={"name": "待删除", "type": "text"},
    )

    # 获取 ID
    list_response = await async_client.get(
        "/api/v1/object/custom_property",
        headers=auth_headers,
    )
    prop_id = next(p["id"] for p in list_response.json() if p["name"] == "待删除")

    # 删除
    response = await async_client.delete(
        f"/api/v1/object/custom_property/{prop_id}",
        headers=auth_headers,
    )
    assert response.status_code == 204

    # 验证已删除
    list_response = await async_client.get(
        "/api/v1/object/custom_property",
        headers=auth_headers,
    )
    prop_names = [p["name"] for p in list_response.json()]
    assert "待删除" not in prop_names


@pytest.mark.asyncio
async def test_delete_custom_property_not_found(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """测试删除不存在的属性返回 404"""
    fake_id = str(uuid4())
    response = await async_client.delete(
        f"/api/v1/object/custom_property/{fake_id}",
        headers=auth_headers,
    )
    assert response.status_code == 404
