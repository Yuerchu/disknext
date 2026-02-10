"""
JWT 工具的单元测试
"""
from datetime import timedelta, datetime, timezone
from uuid import uuid4, UUID

import jwt as pyjwt
import pytest

from sqlmodels.group import GroupClaims
from utils.JWT import create_access_token, create_refresh_token, build_token_payload


# 测试用的 GroupClaims
def _make_group_claims(admin: bool = False) -> GroupClaims:
    return GroupClaims(
        id=uuid4(),
        name="测试组",
        max_storage=1073741824,
        share_enabled=True,
        web_dav_enabled=False,
        admin=admin,
        speed_limit=0,
    )


# 设置测试用的密钥
@pytest.fixture(autouse=True)
def setup_secret_key():
    """为测试设置密钥"""
    import utils.JWT as jwt_module
    jwt_module.SECRET_KEY = "test_secret_key_for_unit_tests"
    yield


def test_create_access_token():
    """测试访问令牌创建"""
    sub = uuid4()
    jti = uuid4()
    group = _make_group_claims()

    result = create_access_token(sub=sub, jti=jti, status="active", group=group)

    assert isinstance(result.access_token, str)
    assert isinstance(result.access_expires, datetime)

    # 解码验证
    decoded = pyjwt.decode(result.access_token, "test_secret_key_for_unit_tests", algorithms=["HS256"])
    assert decoded["sub"] == str(sub)
    assert decoded["jti"] == str(jti)
    assert decoded["status"] == "active"
    assert decoded["group"]["admin"] is False
    assert "exp" in decoded


def test_create_access_token_custom_expiry():
    """测试自定义过期时间"""
    sub = uuid4()
    jti = uuid4()
    group = _make_group_claims()
    custom_expiry = timedelta(minutes=30)

    result = create_access_token(sub=sub, jti=jti, status="active", group=group, expires_delta=custom_expiry)

    decoded = pyjwt.decode(result.access_token, "test_secret_key_for_unit_tests", algorithms=["HS256"])

    # 验证过期时间大约是30分钟后
    exp_timestamp = decoded["exp"]
    now_timestamp = datetime.now(timezone.utc).timestamp()

    # 允许1秒误差
    assert abs(exp_timestamp - now_timestamp - 1800) < 1


def test_create_access_token_default_expiry():
    """测试访问令牌默认1小时过期"""
    sub = uuid4()
    jti = uuid4()
    group = _make_group_claims()

    result = create_access_token(sub=sub, jti=jti, status="active", group=group)

    decoded = pyjwt.decode(result.access_token, "test_secret_key_for_unit_tests", algorithms=["HS256"])

    # 验证过期时间大约是1小时后
    exp_timestamp = decoded["exp"]
    now_timestamp = datetime.now(timezone.utc).timestamp()

    # 允许1秒误差
    assert abs(exp_timestamp - now_timestamp - 3600) < 1


def test_create_refresh_token():
    """测试刷新令牌创建"""
    sub = uuid4()
    jti = uuid4()

    result = create_refresh_token(sub=sub, jti=jti)

    assert isinstance(result.refresh_token, str)
    assert isinstance(result.refresh_expires, datetime)

    # 解码验证
    decoded = pyjwt.decode(result.refresh_token, "test_secret_key_for_unit_tests", algorithms=["HS256"])
    assert decoded["sub"] == str(sub)
    assert decoded["token_type"] == "refresh"
    assert "exp" in decoded


def test_create_refresh_token_default_expiry():
    """测试刷新令牌默认30天过期"""
    sub = uuid4()
    jti = uuid4()

    result = create_refresh_token(sub=sub, jti=jti)

    decoded = pyjwt.decode(result.refresh_token, "test_secret_key_for_unit_tests", algorithms=["HS256"])

    # 验证过期时间大约是30天后
    exp_timestamp = decoded["exp"]
    now_timestamp = datetime.now(timezone.utc).timestamp()

    # 30天 = 30 * 24 * 3600 = 2592000 秒
    # 允许1秒误差
    assert abs(exp_timestamp - now_timestamp - 2592000) < 1


def test_access_token_contains_group_claims():
    """测试访问令牌包含完整的 group claims"""
    sub = uuid4()
    jti = uuid4()
    group = _make_group_claims(admin=True)

    result = create_access_token(sub=sub, jti=jti, status="active", group=group)

    decoded = pyjwt.decode(result.access_token, "test_secret_key_for_unit_tests", algorithms=["HS256"])

    assert decoded["group"]["admin"] is True
    assert decoded["group"]["name"] == "测试组"
    assert decoded["group"]["max_storage"] == 1073741824
    assert decoded["group"]["share_enabled"] is True


def test_access_token_does_not_have_token_type():
    """测试访问令牌不包含 token_type"""
    sub = uuid4()
    jti = uuid4()
    group = _make_group_claims()

    result = create_access_token(sub=sub, jti=jti, status="active", group=group)

    decoded = pyjwt.decode(result.access_token, "test_secret_key_for_unit_tests", algorithms=["HS256"])

    assert "token_type" not in decoded


def test_refresh_token_has_token_type():
    """测试刷新令牌包含 token_type"""
    sub = uuid4()
    jti = uuid4()

    result = create_refresh_token(sub=sub, jti=jti)

    decoded = pyjwt.decode(result.refresh_token, "test_secret_key_for_unit_tests", algorithms=["HS256"])

    assert decoded["token_type"] == "refresh"


def test_token_expired():
    """测试令牌过期"""
    sub = uuid4()
    jti = uuid4()
    group = _make_group_claims()

    # 创建一个立即过期的令牌
    result = create_access_token(
        sub=sub, jti=jti, status="active", group=group,
        expires_delta=timedelta(seconds=-1),
    )

    # 尝试解码应该抛出过期异常
    with pytest.raises(pyjwt.ExpiredSignatureError):
        pyjwt.decode(result.access_token, "test_secret_key_for_unit_tests", algorithms=["HS256"])


def test_token_invalid_signature():
    """测试无效签名"""
    sub = uuid4()
    jti = uuid4()
    group = _make_group_claims()

    result = create_access_token(sub=sub, jti=jti, status="active", group=group)

    # 使用错误的密钥解码
    with pytest.raises(pyjwt.InvalidSignatureError):
        pyjwt.decode(result.access_token, "wrong_secret_key", algorithms=["HS256"])
