"""
ServerConfig 模型单元测试

覆盖：
- get_rp_config() 从 site_url 的各种形式解析 WebAuthn RP 配置
- PostgreSQL 触发器对 captcha/oauth 一致性的强制校验

使用 Faker 生成大量随机 URL 进行边界测试。
"""
import pytest
from faker import Faker
from sqlalchemy.exc import DBAPIError
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodels.server_config import CaptchaType, ServerConfig


def _make_config(site_url: str, site_title: str = "DiskNext") -> ServerConfig:
    """构造一个 ServerConfig 实例（不写数据库），仅用于测试纯函数"""
    return ServerConfig(
        site_url=site_url,
        site_title=site_title,
    )


class TestGetRpConfig:
    """ServerConfig.get_rp_config() 的综合测试"""

    def test_https_with_domain(self):
        """HTTPS + 域名应返回 rp_id=域名, origin=scheme://netloc"""
        config = _make_config("https://example.com", "Example")
        rp_id, rp_name, origin = config.get_rp_config()
        assert rp_id == "example.com"
        assert rp_name == "Example"
        assert origin == "https://example.com"

    def test_http_with_domain(self):
        """HTTP + 域名"""
        config = _make_config("http://example.com")
        rp_id, _, origin = config.get_rp_config()
        assert rp_id == "example.com"
        assert origin == "http://example.com"

    def test_https_with_explicit_port(self):
        """带显式端口时 netloc 应包含端口"""
        config = _make_config("https://example.com:8443")
        rp_id, _, origin = config.get_rp_config()
        assert rp_id == "example.com"  # hostname 不含端口
        assert origin == "https://example.com:8443"

    def test_localhost(self):
        """localhost 不带 TLD 也要正确解析"""
        config = _make_config("http://localhost:8080")
        rp_id, _, origin = config.get_rp_config()
        assert rp_id == "localhost"
        assert origin == "http://localhost:8080"

    def test_url_with_path(self):
        """URL 包含路径时 origin 不应包含路径"""
        config = _make_config("https://example.com/path/to/app")
        rp_id, _, origin = config.get_rp_config()
        assert rp_id == "example.com"
        assert origin == "https://example.com"

    def test_url_with_query_string(self):
        """URL 包含 query 时 origin 不应包含 query"""
        config = _make_config("https://example.com?foo=bar")
        rp_id, _, origin = config.get_rp_config()
        assert rp_id == "example.com"
        assert origin == "https://example.com"

    def test_subdomain(self):
        """子域名应作为 rp_id 返回"""
        config = _make_config("https://app.sub.example.com")
        rp_id, _, origin = config.get_rp_config()
        assert rp_id == "app.sub.example.com"
        assert origin == "https://app.sub.example.com"

    def test_uppercase_hostname_lowercased(self):
        """urlparse 返回的 hostname 始终小写"""
        config = _make_config("https://EXAMPLE.COM")
        rp_id, _, _ = config.get_rp_config()
        assert rp_id == "example.com"

    def test_site_title_preserved_as_rp_name(self):
        """rp_name 应与 site_title 完全一致（含 Unicode、表情符号）"""
        config = _make_config(
            site_url="https://example.com",
            site_title="云星启智 🚀 DiskNext",
        )
        _, rp_name, _ = config.get_rp_config()
        assert rp_name == "云星启智 🚀 DiskNext"

    def test_fuzz_with_faker_urls(self, faker: Faker):
        """用 Faker 生成 50 个随机 HTTPS URL，全部应解析成功且三元组字段非空"""
        for _ in range(50):
            domain = faker.domain_name()
            site_url = f"https://{domain}"
            config = _make_config(site_url, faker.company())
            rp_id, rp_name, origin = config.get_rp_config()
            assert rp_id == domain
            assert origin == site_url
            assert rp_name  # 非空

    def test_fuzz_with_faker_ports(self, faker: Faker):
        """随机端口测试"""
        for _ in range(20):
            domain = faker.domain_name()
            port = faker.random_int(min=1024, max=65535)
            site_url = f"https://{domain}:{port}"
            config = _make_config(site_url)
            rp_id, _, origin = config.get_rp_config()
            assert rp_id == domain
            assert origin == site_url

    def test_default_instance(self):
        """使用默认值构造的 ServerConfig 应可用"""
        config = ServerConfig()
        rp_id, rp_name, origin = config.get_rp_config()
        # site_url 默认为 "http://localhost"
        assert rp_id == "localhost"
        assert origin == "http://localhost"
        # site_title 默认为 "云星启智"
        assert rp_name == "云星启智"


# ==================== PostgreSQL 触发器：captcha/oauth 一致性 ====================

async def _insert_config(session: AsyncSession, **kwargs) -> ServerConfig:
    """构造并持久化一个 ServerConfig（绕过 pydantic 的跨字段校验，直达 DB）"""
    config = ServerConfig(**kwargs)
    return await config.save(session)


class TestCaptchaOAuthTrigger:
    """PostgreSQL 触发器的集成测试：INSERT/UPDATE 必须被拦截"""

    # ---------- GCaptcha ----------

    @pytest.mark.asyncio
    async def test_gcaptcha_empty_key_rejected_on_insert(
        self, db_session: AsyncSession
    ):
        """启用 reCAPTCHA 但未填 Site Key → trigger 必须报错"""
        with pytest.raises(DBAPIError) as exc_info:
            await _insert_config(
                db_session,
                captcha_type=CaptchaType.GCAPTCHA,
                captcha_recaptcha_key="",
                captcha_recaptcha_secret="some_secret",
            )
        assert "reCAPTCHA" in str(exc_info.value.orig)
        await db_session.rollback()

    @pytest.mark.asyncio
    async def test_gcaptcha_empty_secret_rejected_on_insert(
        self, db_session: AsyncSession
    ):
        """启用 reCAPTCHA 但未填 Secret Key → trigger 必须报错"""
        with pytest.raises(DBAPIError) as exc_info:
            await _insert_config(
                db_session,
                captcha_type=CaptchaType.GCAPTCHA,
                captcha_recaptcha_key="some_key",
                captcha_recaptcha_secret="",
            )
        assert "reCAPTCHA" in str(exc_info.value.orig)
        await db_session.rollback()

    @pytest.mark.asyncio
    async def test_gcaptcha_both_filled_allowed(
        self, db_session: AsyncSession, faker: Faker
    ):
        """启用 reCAPTCHA 且 key/secret 均非空 → 允许"""
        config = await _insert_config(
            db_session,
            captcha_type=CaptchaType.GCAPTCHA,
            captcha_recaptcha_key=faker.pystr(min_chars=20, max_chars=40),
            captcha_recaptcha_secret=faker.pystr(min_chars=20, max_chars=40),
        )
        assert config.id is not None

    # ---------- Cloudflare Turnstile ----------

    @pytest.mark.asyncio
    async def test_turnstile_empty_key_rejected(
        self, db_session: AsyncSession
    ):
        with pytest.raises(DBAPIError) as exc_info:
            await _insert_config(
                db_session,
                captcha_type=CaptchaType.CLOUD_FLARE_TURNSTILE,
                captcha_cloudflare_key="",
                captcha_cloudflare_secret="secret_xyz",
            )
        assert "Cloudflare Turnstile" in str(exc_info.value.orig)
        await db_session.rollback()

    @pytest.mark.asyncio
    async def test_turnstile_empty_secret_rejected(
        self, db_session: AsyncSession
    ):
        with pytest.raises(DBAPIError) as exc_info:
            await _insert_config(
                db_session,
                captcha_type=CaptchaType.CLOUD_FLARE_TURNSTILE,
                captcha_cloudflare_key="key_abc",
                captcha_cloudflare_secret="",
            )
        assert "Cloudflare Turnstile" in str(exc_info.value.orig)
        await db_session.rollback()

    @pytest.mark.asyncio
    async def test_turnstile_both_filled_allowed(
        self, db_session: AsyncSession, faker: Faker
    ):
        config = await _insert_config(
            db_session,
            captcha_type=CaptchaType.CLOUD_FLARE_TURNSTILE,
            captcha_cloudflare_key=faker.pystr(min_chars=20, max_chars=40),
            captcha_cloudflare_secret=faker.pystr(min_chars=20, max_chars=40),
        )
        assert config.id is not None

    # ---------- GitHub OAuth ----------

    @pytest.mark.asyncio
    async def test_github_enabled_without_client_id_rejected(
        self, db_session: AsyncSession
    ):
        with pytest.raises(DBAPIError) as exc_info:
            await _insert_config(
                db_session,
                is_github_enabled=True,
                github_client_id="",
                github_client_secret="secret",
            )
        assert "GitHub" in str(exc_info.value.orig)
        await db_session.rollback()

    @pytest.mark.asyncio
    async def test_github_enabled_without_secret_rejected(
        self, db_session: AsyncSession
    ):
        with pytest.raises(DBAPIError) as exc_info:
            await _insert_config(
                db_session,
                is_github_enabled=True,
                github_client_id="client_id_xyz",
                github_client_secret="",
            )
        assert "GitHub" in str(exc_info.value.orig)
        await db_session.rollback()

    @pytest.mark.asyncio
    async def test_github_disabled_allows_empty_credentials(
        self, db_session: AsyncSession
    ):
        """未启用 GitHub OAuth 时，空凭证不应被拒绝"""
        config = await _insert_config(
            db_session,
            is_github_enabled=False,
            github_client_id="",
            github_client_secret="",
        )
        assert config.id is not None

    @pytest.mark.asyncio
    async def test_github_enabled_with_both_credentials_allowed(
        self, db_session: AsyncSession, faker: Faker
    ):
        config = await _insert_config(
            db_session,
            is_github_enabled=True,
            github_client_id=faker.pystr(min_chars=20, max_chars=40),
            github_client_secret=faker.pystr(min_chars=30, max_chars=80),
        )
        assert config.id is not None

    # ---------- QQ OAuth ----------

    @pytest.mark.asyncio
    async def test_qq_enabled_without_app_id_rejected(
        self, db_session: AsyncSession
    ):
        with pytest.raises(DBAPIError) as exc_info:
            await _insert_config(
                db_session,
                is_qq_enabled=True,
                qq_client_id="",
                qq_client_secret="app_key",
            )
        assert "QQ" in str(exc_info.value.orig)
        await db_session.rollback()

    @pytest.mark.asyncio
    async def test_qq_enabled_without_app_key_rejected(
        self, db_session: AsyncSession
    ):
        with pytest.raises(DBAPIError) as exc_info:
            await _insert_config(
                db_session,
                is_qq_enabled=True,
                qq_client_id="app_id",
                qq_client_secret="",
            )
        assert "QQ" in str(exc_info.value.orig)
        await db_session.rollback()

    @pytest.mark.asyncio
    async def test_qq_enabled_with_both_credentials_allowed(
        self, db_session: AsyncSession, faker: Faker
    ):
        config = await _insert_config(
            db_session,
            is_qq_enabled=True,
            qq_client_id=faker.numerify("##########"),
            qq_client_secret=faker.pystr(min_chars=30, max_chars=80),
        )
        assert config.id is not None

    # ---------- UPDATE 场景 ----------

    @pytest.mark.asyncio
    async def test_update_to_invalid_state_rejected(
        self, db_session: AsyncSession, faker: Faker
    ):
        """先写入合法行，再 UPDATE 成非法状态 → trigger 必须拦截"""
        config = await _insert_config(
            db_session,
            is_github_enabled=False,
        )

        config.is_github_enabled = True
        config.github_client_id = ""
        config.github_client_secret = ""

        with pytest.raises(DBAPIError) as exc_info:
            await config.save(db_session)
        assert "GitHub" in str(exc_info.value.orig)
        await db_session.rollback()

    @pytest.mark.asyncio
    async def test_update_stays_valid_when_disabling_provider(
        self, db_session: AsyncSession, faker: Faker
    ):
        """把 is_github_enabled 改回 false，允许清空凭证"""
        config = await _insert_config(
            db_session,
            is_github_enabled=True,
            github_client_id=faker.pystr(min_chars=20, max_chars=40),
            github_client_secret=faker.pystr(min_chars=30, max_chars=60),
        )

        config.is_github_enabled = False
        config.github_client_id = ""
        config.github_client_secret = ""
        updated = await config.save(db_session)
        assert updated.is_github_enabled is False

    # ---------- 多条件组合 ----------

    @pytest.mark.asyncio
    async def test_multiple_providers_all_valid(
        self, db_session: AsyncSession, faker: Faker
    ):
        """同时启用 reCAPTCHA + GitHub + QQ，全部合法 → 允许"""
        config = await _insert_config(
            db_session,
            captcha_type=CaptchaType.GCAPTCHA,
            captcha_recaptcha_key=faker.pystr(min_chars=20, max_chars=40),
            captcha_recaptcha_secret=faker.pystr(min_chars=20, max_chars=40),
            is_github_enabled=True,
            github_client_id=faker.pystr(min_chars=20, max_chars=40),
            github_client_secret=faker.pystr(min_chars=30, max_chars=60),
            is_qq_enabled=True,
            qq_client_id=faker.numerify("##########"),
            qq_client_secret=faker.pystr(min_chars=30, max_chars=60),
        )
        assert config.id is not None

    @pytest.mark.asyncio
    async def test_first_failing_rule_reported(
        self, db_session: AsyncSession, faker: Faker
    ):
        """多个规则同时违反时，trigger 按声明顺序报告第一个错误（captcha 优先）"""
        with pytest.raises(DBAPIError) as exc_info:
            await _insert_config(
                db_session,
                captcha_type=CaptchaType.GCAPTCHA,
                captcha_recaptcha_key="",
                captcha_recaptcha_secret="",
                is_github_enabled=True,
                github_client_id="",
                github_client_secret="",
            )
        # 触发顺序：captcha 先于 oauth，第一个报 reCAPTCHA
        assert "reCAPTCHA" in str(exc_info.value.orig)
        await db_session.rollback()

    # ---------- Fuzz ----------

    @pytest.mark.asyncio
    async def test_fuzz_random_valid_configs(
        self, db_session: AsyncSession, faker: Faker
    ):
        """随机生成 5 组合法配置，全部应允许写入"""
        for _ in range(5):
            config = await _insert_config(
                db_session,
                captcha_type=faker.random_element([
                    CaptchaType.DEFAULT,
                    CaptchaType.GCAPTCHA,
                    CaptchaType.CLOUD_FLARE_TURNSTILE,
                ]),
                captcha_recaptcha_key=faker.pystr(min_chars=20, max_chars=40),
                captcha_recaptcha_secret=faker.pystr(min_chars=20, max_chars=40),
                captcha_cloudflare_key=faker.pystr(min_chars=20, max_chars=40),
                captcha_cloudflare_secret=faker.pystr(min_chars=20, max_chars=40),
                is_github_enabled=faker.boolean(),
                github_client_id=faker.pystr(min_chars=20, max_chars=40),
                github_client_secret=faker.pystr(min_chars=30, max_chars=60),
                is_qq_enabled=faker.boolean(),
                qq_client_id=faker.numerify("##########"),
                qq_client_secret=faker.pystr(min_chars=30, max_chars=60),
            )
            assert config.id is not None
            # 每个 insert 后需要 rollback/清理，避免测试数据相互影响
            await db_session.delete(config)
            await db_session.commit()
