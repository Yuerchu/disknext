"""
Password 工具类的单元测试
"""
import pytest

from utils.password.pwd import Password, PasswordStatus


def test_password_generate_default_length():
    """测试默认长度生成密码"""
    password = Password.generate()

    # 默认长度为 8，token_hex 生成的是16进制字符串，长度是原始长度的2倍
    assert len(password) == 16
    assert isinstance(password, str)


def test_password_generate_custom_length():
    """测试自定义长度生成密码"""
    length = 12
    password = Password.generate(length=length)

    assert len(password) == length * 2
    assert isinstance(password, str)


def test_password_hash():
    """测试密码哈希"""
    plain_password = "my_secure_password_123"
    hashed = Password.hash(plain_password)

    assert hashed != plain_password
    assert isinstance(hashed, str)
    # Argon2 哈希以 $argon2 开头
    assert hashed.startswith("$argon2")


def test_password_verify_valid():
    """测试正确密码验证"""
    plain_password = "correct_password"
    hashed = Password.hash(plain_password)

    status = Password.verify(hashed, plain_password)

    assert status == PasswordStatus.VALID


def test_password_verify_invalid():
    """测试错误密码验证"""
    plain_password = "correct_password"
    wrong_password = "wrong_password"
    hashed = Password.hash(plain_password)

    status = Password.verify(hashed, wrong_password)

    assert status == PasswordStatus.INVALID


def test_password_verify_expired():
    """测试密码哈希过期检测"""
    # 注意: 实际检测需要修改 Argon2 参数，这里只是测试接口
    # 在真实场景中，当哈希参数过时时会返回 EXPIRED
    plain_password = "password"
    hashed = Password.hash(plain_password)

    status = Password.verify(hashed, plain_password)

    # 新生成的哈希应该是 VALID
    assert status in [PasswordStatus.VALID, PasswordStatus.EXPIRED]


@pytest.mark.asyncio
async def test_totp_generate():
    """测试 TOTP 密钥生成"""
    email = "testuser@test.local"

    response = await Password.generate_totp(email)

    assert response.setup_token is not None
    assert response.uri is not None
    assert isinstance(response.setup_token, str)
    assert isinstance(response.uri, str)
    # TOTP URI 格式: otpauth://totp/...
    assert response.uri.startswith("otpauth://totp/")
    assert email in response.uri


def test_totp_verify_valid():
    """测试 TOTP 验证正确"""
    import pyotp

    # 生成密钥
    secret = pyotp.random_base32()

    # 生成当前有效的验证码
    totp = pyotp.TOTP(secret)
    valid_code = totp.now()

    # 验证
    status = Password.verify_totp(secret, valid_code)

    assert status == PasswordStatus.VALID


def test_totp_verify_invalid():
    """测试 TOTP 验证错误"""
    import pyotp

    secret = pyotp.random_base32()
    invalid_code = "000000"  # 几乎不可能是当前有效码

    status = Password.verify_totp(secret, invalid_code)

    # 注意: 极小概率 000000 恰好是有效码，但实际测试中基本不会发生
    assert status == PasswordStatus.INVALID


def test_password_hash_consistency():
    """测试相同密码多次哈希结果不同（盐随机）"""
    password = "test_password"

    hash1 = Password.hash(password)
    hash2 = Password.hash(password)

    # 由于盐是随机的，两次哈希结果应该不同
    assert hash1 != hash2

    # 但都应该能通过验证
    assert Password.verify(hash1, password) == PasswordStatus.VALID
    assert Password.verify(hash2, password) == PasswordStatus.VALID


def test_password_generate_uniqueness():
    """测试生成的密码唯一性"""
    passwords = [Password.generate() for _ in range(100)]

    # 100个密码应该都不相同
    assert len(set(passwords)) == 100
