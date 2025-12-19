"""
JWT 工具的单元测试
"""
import time
from datetime import timedelta, datetime, timezone

import jwt as pyjwt
import pytest

from utils.JWT.JWT import create_access_token, create_refresh_token, SECRET_KEY


# 设置测试用的密钥
@pytest.fixture(autouse=True)
def setup_secret_key():
    """为测试设置密钥"""
    import utils.JWT.JWT as jwt_module
    jwt_module.SECRET_KEY = "test_secret_key_for_unit_tests"
    yield
    # 测试后恢复（虽然在单元测试中不太重要）


def test_create_access_token():
    """测试访问令牌创建"""
    data = {"sub": "testuser", "role": "user"}

    token, expire_time = create_access_token(data)

    assert isinstance(token, str)
    assert isinstance(expire_time, datetime)

    # 解码验证
    decoded = pyjwt.decode(token, "test_secret_key_for_unit_tests", algorithms=["HS256"])
    assert decoded["sub"] == "testuser"
    assert decoded["role"] == "user"
    assert "exp" in decoded


def test_create_access_token_custom_expiry():
    """测试自定义过期时间"""
    data = {"sub": "testuser"}
    custom_expiry = timedelta(hours=1)

    token, expire_time = create_access_token(data, expires_delta=custom_expiry)

    decoded = pyjwt.decode(token, "test_secret_key_for_unit_tests", algorithms=["HS256"])

    # 验证过期时间大约是1小时后
    exp_timestamp = decoded["exp"]
    now_timestamp = datetime.now(timezone.utc).timestamp()

    # 允许1秒误差
    assert abs(exp_timestamp - now_timestamp - 3600) < 1


def test_create_refresh_token():
    """测试刷新令牌创建"""
    data = {"sub": "testuser"}

    token, expire_time = create_refresh_token(data)

    assert isinstance(token, str)
    assert isinstance(expire_time, datetime)

    # 解码验证
    decoded = pyjwt.decode(token, "test_secret_key_for_unit_tests", algorithms=["HS256"])
    assert decoded["sub"] == "testuser"
    assert decoded["token_type"] == "refresh"
    assert "exp" in decoded


def test_create_refresh_token_default_expiry():
    """测试刷新令牌默认30天过期"""
    data = {"sub": "testuser"}

    token, expire_time = create_refresh_token(data)

    decoded = pyjwt.decode(token, "test_secret_key_for_unit_tests", algorithms=["HS256"])

    # 验证过期时间大约是30天后
    exp_timestamp = decoded["exp"]
    now_timestamp = datetime.now(timezone.utc).timestamp()

    # 30天 = 30 * 24 * 3600 = 2592000 秒
    # 允许1秒误差
    assert abs(exp_timestamp - now_timestamp - 2592000) < 1


def test_token_decode():
    """测试令牌解码"""
    data = {"sub": "user123", "email": "user@example.com"}

    token, _ = create_access_token(data)

    # 解码
    decoded = pyjwt.decode(token, "test_secret_key_for_unit_tests", algorithms=["HS256"])

    assert decoded["sub"] == "user123"
    assert decoded["email"] == "user@example.com"


def test_token_expired():
    """测试令牌过期"""
    data = {"sub": "testuser"}

    # 创建一个立即过期的令牌
    token, _ = create_access_token(data, expires_delta=timedelta(seconds=-1))

    # 尝试解码应该抛出过期异常
    with pytest.raises(pyjwt.ExpiredSignatureError):
        pyjwt.decode(token, "test_secret_key_for_unit_tests", algorithms=["HS256"])


def test_token_invalid_signature():
    """测试无效签名"""
    data = {"sub": "testuser"}

    token, _ = create_access_token(data)

    # 使用错误的密钥解码
    with pytest.raises(pyjwt.InvalidSignatureError):
        pyjwt.decode(token, "wrong_secret_key", algorithms=["HS256"])


def test_access_token_does_not_have_token_type():
    """测试访问令牌不包含 token_type"""
    data = {"sub": "testuser"}

    token, _ = create_access_token(data)

    decoded = pyjwt.decode(token, "test_secret_key_for_unit_tests", algorithms=["HS256"])

    assert "token_type" not in decoded


def test_refresh_token_has_token_type():
    """测试刷新令牌包含 token_type"""
    data = {"sub": "testuser"}

    token, _ = create_refresh_token(data)

    decoded = pyjwt.decode(token, "test_secret_key_for_unit_tests", algorithms=["HS256"])

    assert decoded["token_type"] == "refresh"


def test_token_payload_preserved():
    """测试自定义负载保留"""
    data = {
        "sub": "user123",
        "name": "Test User",
        "roles": ["admin", "user"],
        "metadata": {"key": "value"}
    }

    token, _ = create_access_token(data)

    decoded = pyjwt.decode(token, "test_secret_key_for_unit_tests", algorithms=["HS256"])

    assert decoded["sub"] == "user123"
    assert decoded["name"] == "Test User"
    assert decoded["roles"] == ["admin", "user"]
    assert decoded["metadata"] == {"key": "value"}
