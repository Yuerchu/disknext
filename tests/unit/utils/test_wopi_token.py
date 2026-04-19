"""
WOPI Token 单元测试

测试 WOPI 访问令牌的生成和验证。
"""
from uuid import uuid4

import pytest

import utils.conf.appmeta as appmeta
from utils.JWT.wopi_token import create_wopi_token, verify_wopi_token

# 确保测试 secret key
appmeta.secret_key = "55dd5c582b21b96b81b0421d6e25507877839e64434d704c89db8ef90e4077d8"


class TestWopiToken:
    """WOPI Token 测试"""

    def test_create_and_verify_token(self) -> None:
        """创建和验证令牌"""
        file_id = uuid4()
        user_id = uuid4()

        token, ttl = create_wopi_token(file_id, user_id, can_write=True)

        assert isinstance(token, str)
        assert isinstance(ttl, int)
        assert ttl > 0

        payload = verify_wopi_token(token)
        assert payload is not None
        assert payload.file_id == file_id
        assert payload.user_id == user_id
        assert payload.can_write is True

    def test_verify_read_only_token(self) -> None:
        """验证只读令牌"""
        file_id = uuid4()
        user_id = uuid4()

        token, ttl = create_wopi_token(file_id, user_id, can_write=False)

        payload = verify_wopi_token(token)
        assert payload is not None
        assert payload.can_write is False

    def test_verify_invalid_token(self) -> None:
        """验证无效令牌返回 None"""
        payload = verify_wopi_token("invalid_token_string")
        assert payload is None

    def test_verify_non_wopi_token(self) -> None:
        """验证非 WOPI 类型令牌返回 None"""
        import jwt as pyjwt
        # 创建一个不含 type=wopi 的令牌
        token = pyjwt.encode(
            {"file_id": str(uuid4()), "user_id": str(uuid4()), "type": "download"},
            appmeta.secret_key,
            algorithm="HS256",
        )
        payload = verify_wopi_token(token)
        assert payload is None

    def test_ttl_is_future_milliseconds(self) -> None:
        """TTL 应为未来的毫秒时间戳"""
        import time

        file_id = uuid4()
        user_id = uuid4()
        token, ttl = create_wopi_token(file_id, user_id)

        current_ms = int(time.time() * 1000)
        # TTL 应大于当前时间
        assert ttl > current_ms
        # TTL 不应超过 11 小时后（10h + 余量）
        assert ttl < current_ms + 11 * 3600 * 1000
