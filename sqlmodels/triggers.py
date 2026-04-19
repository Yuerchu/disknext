"""
PostgreSQL 触发器定义

本模块集中声明所有下沉到数据库层的业务约束触发器，通过 SQLAlchemy 的
``after_create`` / ``before_drop`` 事件挂载到对应的 Table 上：

- 走 ``SQLModel.metadata.create_all`` 时（开发/测试环境），建表后自动创建 trigger
- 未来引入 Alembic 迁移时，同样可被 autogenerate 识别并生成 DDL
- ``.execute_if(dialect='postgresql')`` 保证仅在 PostgreSQL 方言下执行

新增触发器时遵循以下模式：

1. 将 PL/pgSQL 函数与 CREATE TRIGGER 语句定义为模块级字符串常量
2. 在模块末尾用 ``event.listen(Table, "after_create", DDL(...).execute_if(...))``
   挂载 after_create，对应用 ``before_drop`` 清理 function 和 trigger
3. 在本模块的 ``__all__`` 中暴露给外部引用（如测试）

本模块被 ``sqlmodels/__init__.py`` 显式导入，确保应用启动时 event listener
在 metadata.create_all 之前被注册。
"""
from sqlalchemy import DDL, event

from .server_config import ServerConfig
from .user import User
from .user_authn import UserAuthn


# ==================== ServerConfig: captcha / oauth 一致性 ====================
#
# 业务规则：
#   1. captcha_type = 'gcaptcha'             → recaptcha key/secret 非空
#   2. captcha_type = 'cloudflare turnstile' → cloudflare key/secret 非空
#   3. is_github_enabled = true              → github client_id/secret 非空
#   4. is_qq_enabled    = true               → qq client_id/secret 非空
#
# 使用 BEFORE INSERT OR UPDATE 触发器而非 CHECK CONSTRAINT 的原因：
# 需要返回带有业务语义的中文错误消息，CHECK 只能返回通用的 "check_violation"。

_SERVERCONFIG_CAPTCHA_OAUTH_FN = """
CREATE OR REPLACE FUNCTION serverconfig_check_captcha_oauth_consistency()
RETURNS TRIGGER AS $fn$
BEGIN
    -- Captcha 一致性
    -- 注意：captcha_type 列类型是 PG enum，SQLAlchemy 默认按 Python enum
    -- 的成员名（name，大写）序列化，因此这里比较的是 'GCAPTCHA' 而非
    -- CaptchaType.GCAPTCHA.value 的小写字面量。
    IF NEW.captcha_type = 'GCAPTCHA' THEN
        IF coalesce(NEW.captcha_recaptcha_key, '') = ''
           OR coalesce(NEW.captcha_recaptcha_secret, '') = '' THEN
            RAISE EXCEPTION '启用 reCAPTCHA 时，Site Key 和 Secret Key 不能为空'
                USING ERRCODE = 'check_violation';
        END IF;
    ELSIF NEW.captcha_type = 'CLOUD_FLARE_TURNSTILE' THEN
        IF coalesce(NEW.captcha_cloudflare_key, '') = ''
           OR coalesce(NEW.captcha_cloudflare_secret, '') = '' THEN
            RAISE EXCEPTION '启用 Cloudflare Turnstile 时，Site Key 和 Secret Key 不能为空'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    -- GitHub OAuth 一致性
    IF NEW.is_github_enabled THEN
        IF coalesce(NEW.github_client_id, '') = ''
           OR coalesce(NEW.github_client_secret, '') = '' THEN
            RAISE EXCEPTION '启用 GitHub OAuth 时，Client ID 和 Client Secret 不能为空'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    -- QQ OAuth 一致性
    IF NEW.is_qq_enabled THEN
        IF coalesce(NEW.qq_client_id, '') = ''
           OR coalesce(NEW.qq_client_secret, '') = '' THEN
            RAISE EXCEPTION '启用 QQ OAuth 时，App ID 和 App Key 不能为空'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;
"""

_SERVERCONFIG_CAPTCHA_OAUTH_TRIGGER_DROP_OLD = (
    "DROP TRIGGER IF EXISTS serverconfig_captcha_oauth_consistency_trg ON serverconfig"
)

_SERVERCONFIG_CAPTCHA_OAUTH_TRIGGER_CREATE = """
CREATE TRIGGER serverconfig_captcha_oauth_consistency_trg
BEFORE INSERT OR UPDATE ON serverconfig
FOR EACH ROW
EXECUTE FUNCTION serverconfig_check_captcha_oauth_consistency()
"""

_SERVERCONFIG_CAPTCHA_OAUTH_FN_DROP = (
    "DROP FUNCTION IF EXISTS serverconfig_check_captcha_oauth_consistency()"
)


# asyncpg 不支持在单次 prepared statement 中执行多条 SQL，因此拆成独立的
# DDL 事件监听器。顺序：function → (drop old trigger) → create trigger
event.listen(
    ServerConfig.__table__,
    "after_create",
    DDL(_SERVERCONFIG_CAPTCHA_OAUTH_FN).execute_if(dialect='postgresql'),
)

event.listen(
    ServerConfig.__table__,
    "after_create",
    DDL(_SERVERCONFIG_CAPTCHA_OAUTH_TRIGGER_DROP_OLD).execute_if(dialect='postgresql'),
)

event.listen(
    ServerConfig.__table__,
    "after_create",
    DDL(_SERVERCONFIG_CAPTCHA_OAUTH_TRIGGER_CREATE).execute_if(dialect='postgresql'),
)

event.listen(
    ServerConfig.__table__,
    "before_drop",
    DDL(_SERVERCONFIG_CAPTCHA_OAUTH_TRIGGER_DROP_OLD).execute_if(dialect='postgresql'),
)

event.listen(
    ServerConfig.__table__,
    "before_drop",
    DDL(_SERVERCONFIG_CAPTCHA_OAUTH_FN_DROP).execute_if(dialect='postgresql'),
)


# ==================== User: 至少一种登录方式 ====================
#
# 业务规则：
#   用户必须至少保有一种可用的登录方式。
#   password_hash / phone / github_id / qq_id 至少一个非空，
#   或者 userauthn 表中存在关联的 Passkey 凭证。
#
# 两个触发器协同：
#   1. user BEFORE UPDATE — 防止把 User 行上最后一个认证字段清空
#   2. userauthn BEFORE DELETE — 防止删除最后一把 Passkey

_USER_AUTH_FN = '''
CREATE OR REPLACE FUNCTION user_check_auth_method()
RETURNS TRIGGER AS $fn$
BEGIN
    IF NEW.password_hash IS NULL
       AND NEW.phone IS NULL
       AND NEW.github_id IS NULL
       AND NEW.qq_id IS NULL
       AND NOT EXISTS (SELECT 1 FROM userauthn WHERE user_id = NEW.id)
    THEN
        RAISE EXCEPTION '用户必须至少有一种登录方式'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;
'''

_USER_AUTH_TRG_DROP = 'DROP TRIGGER IF EXISTS user_auth_method_trg ON "user"'

_USER_AUTH_TRG_CREATE = '''
CREATE TRIGGER user_auth_method_trg
BEFORE UPDATE ON "user"
FOR EACH ROW
EXECUTE FUNCTION user_check_auth_method()
'''

_USER_AUTH_FN_DROP = "DROP FUNCTION IF EXISTS user_check_auth_method()"

for _ddl in (_USER_AUTH_FN, _USER_AUTH_TRG_DROP, _USER_AUTH_TRG_CREATE):
    event.listen(User.__table__, "after_create", DDL(_ddl).execute_if(dialect='postgresql'))
for _ddl in (_USER_AUTH_TRG_DROP, _USER_AUTH_FN_DROP):
    event.listen(User.__table__, "before_drop", DDL(_ddl).execute_if(dialect='postgresql'))


# ==================== UserAuthn: 防止删除最后一个认证方式 ====================

_AUTHN_LAST_AUTH_FN = '''
CREATE OR REPLACE FUNCTION userauthn_check_last_auth()
RETURNS TRIGGER AS $fn$
DECLARE
    remaining int;
    has_other bool;
BEGIN
    SELECT count(*) INTO remaining
    FROM userauthn WHERE user_id = OLD.user_id AND id != OLD.id;

    SELECT (password_hash IS NOT NULL OR phone IS NOT NULL
            OR github_id IS NOT NULL OR qq_id IS NOT NULL)
    INTO has_other
    FROM "user" WHERE id = OLD.user_id;

    IF remaining = 0 AND NOT COALESCE(has_other, FALSE) THEN
        RAISE EXCEPTION '不能删除最后一个认证方式'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN OLD;
END;
$fn$ LANGUAGE plpgsql;
'''

_AUTHN_LAST_AUTH_TRG_DROP = "DROP TRIGGER IF EXISTS userauthn_last_auth_trg ON userauthn"

_AUTHN_LAST_AUTH_TRG_CREATE = '''
CREATE TRIGGER userauthn_last_auth_trg
BEFORE DELETE ON userauthn
FOR EACH ROW
EXECUTE FUNCTION userauthn_check_last_auth()
'''

_AUTHN_LAST_AUTH_FN_DROP = "DROP FUNCTION IF EXISTS userauthn_check_last_auth()"

for _ddl in (_AUTHN_LAST_AUTH_FN, _AUTHN_LAST_AUTH_TRG_DROP, _AUTHN_LAST_AUTH_TRG_CREATE):
    event.listen(UserAuthn.__table__, "after_create", DDL(_ddl).execute_if(dialect='postgresql'))
for _ddl in (_AUTHN_LAST_AUTH_TRG_DROP, _AUTHN_LAST_AUTH_FN_DROP):
    event.listen(UserAuthn.__table__, "before_drop", DDL(_ddl).execute_if(dialect='postgresql'))
