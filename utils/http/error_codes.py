"""
机器可读错误代码

前端据此查找本地化消息。格式: ``domain.specific_error``

约定：一旦发布，代码值不可变更（前端依赖）。
"""
from enum import StrEnum


class ErrorCode(StrEnum):
    """DiskNext 错误代码枚举"""

    # ==================== common ====================

    NOT_IMPLEMENTED = "common.not_implemented"
    """功能尚未实现"""

    INTERNAL_ERROR = "common.internal_error"
    """服务器内部错误"""

    # ==================== auth ====================

    AUTH_INVALID_CREDENTIALS = "auth.invalid_credentials"
    """凭据无效（密码错误、token 过期等）"""

    AUTH_ACCOUNT_DISABLED = "auth.account_disabled"
    """账户已被禁用"""

    AUTH_TWO_FA_REQUIRED = "auth.two_fa_required"
    """需要两步验证"""

    AUTH_TWO_FA_INVALID = "auth.two_fa_invalid"
    """两步验证码错误"""

    AUTH_PROVIDER_DISABLED = "auth.provider_disabled"
    """登录方式未启用"""

    AUTH_PROVIDER_UNSUPPORTED = "auth.provider_unsupported"
    """不支持的登录方式"""

    AUTH_OAUTH_NOT_CONFIGURED = "auth.oauth_not_configured"
    """OAuth 未配置"""

    AUTH_REFRESH_TOKEN_INVALID = "auth.refresh_token_invalid"
    """刷新令牌无效或已过期"""

    AUTH_REFRESH_TOKEN_TYPE = "auth.refresh_token_type_mismatch"
    """非刷新令牌"""

    AUTH_TOKEN_MISSING_SUB = "auth.token_missing_subject"
    """令牌缺少用户标识"""

    AUTH_DOWNLOAD_TOKEN_INVALID = "auth.download_token_invalid"
    """下载令牌无效"""

    AUTH_PASSKEY_DISABLED = "auth.passkey_disabled"
    """Passkey 未启用"""

    AUTH_PASSKEY_ASSERTION_EMPTY = "auth.passkey_assertion_empty"
    """WebAuthn assertion response 为空"""

    AUTH_PASSKEY_CHALLENGE_EXPIRED = "auth.passkey_challenge_expired"
    """登录会话已过期"""

    AUTH_PASSKEY_CREDENTIAL_MISSING = "auth.passkey_credential_missing"
    """缺少凭证 ID"""

    AUTH_PASSKEY_NOT_REGISTERED = "auth.passkey_not_registered"
    """Passkey 凭证未注册"""

    AUTH_PASSKEY_VERIFICATION_FAILED = "auth.passkey_verification_failed"
    """Passkey 验证失败"""

    AUTH_PASSKEY_REGISTER_EXPIRED = "auth.passkey_register_session_expired"
    """注册会话已过期"""

    # ==================== mail ====================

    MAIL_SMTP_ERROR = "mail.smtp_error"
    """SMTP 发送失败"""

    MAIL_TEMPLATE_NOT_FOUND = "mail.template_not_found"
    """邮件模板不存在"""

    MAIL_RATE_LIMITED = "mail.rate_limited"
    """验证码发送过于频繁"""

    MAIL_CODE_INVALID = "mail.code_invalid"
    """验证码错误或已过期"""

    # ==================== sms ====================

    SMS_PROVIDER_ERROR = "sms.provider_error"
    """短信提供商发送失败"""

    SMS_RATE_LIMITED = "sms.rate_limited"
    """短信发送过于频繁"""

    SMS_CODE_INVALID = "sms.code_invalid"
    """短信验证码错误或已过期"""

    SMS_NO_PROVIDER = "sms.no_provider_configured"
    """未配置短信提供商"""

    SMS_PROVIDER_NOT_FOUND = "sms.provider_not_found"
    """短信提供商不存在"""

    SMS_PROVIDER_NAME_EXISTS = "sms.provider_name_exists"
    """短信提供商名称已存在"""

    # ==================== user ====================

    USER_NOT_FOUND = "user.not_found"
    """用户不存在"""

    USER_EMAIL_EXISTS = "user.email_exists"
    """该邮箱已被注册"""

    USER_EMAIL_NOT_REGISTERED = "user.email_not_registered"
    """该邮箱未注册"""

    USER_REGISTRATION_CLOSED = "user.registration_closed"
    """注册功能未开放"""

    USER_PASSWORD_EMPTY = "user.password_empty"
    """密码不能为空"""

    USER_REGISTRATION_UNSUPPORTED = "user.registration_unsupported"
    """不支持的注册方式"""

    # ==================== user_settings ====================

    USER_SETTINGS_PASSWORD_NOT_SET = "user_settings.password_not_set"
    """未设置密码"""

    USER_SETTINGS_PASSWORD_WRONG = "user_settings.current_password_wrong"
    """当前密码错误"""

    USER_SETTINGS_OPTION_REQUIRED = "user_settings.option_value_required"
    """设置项不允许为空"""

    USER_SETTINGS_GRAVATAR_NO_EMAIL = "user_settings.gravatar_requires_email"
    """Gravatar 需要邮箱"""

    USER_SETTINGS_TOTP_SESSION_EXPIRED = "user_settings.totp_setup_expired"
    """TOTP 设置会话已过期"""

    USER_SETTINGS_TOTP_INVALID_TOKEN = "user_settings.totp_invalid_token"
    """无效的 TOTP token"""

    USER_SETTINGS_TOTP_INVALID_CODE = "user_settings.totp_invalid_code"
    """无效的 TOTP 验证码"""

    USER_SETTINGS_WEBAUTHN_NOT_FOUND = "user_settings.webauthn_not_found"
    """WebAuthn 凭证不存在"""

    USER_SETTINGS_THEME_NOT_FOUND = "user_settings.theme_not_found"
    """主题预设不存在"""

    USER_SETTINGS_VIEWER_APP_NOT_FOUND = "user_settings.viewer_app_not_found"
    """应用不存在"""

    USER_SETTINGS_VIEWER_EXT_UNSUPPORTED = "user_settings.viewer_ext_unsupported"
    """该应用不支持此扩展名"""

    USER_SETTINGS_VIEWER_DEFAULT_NOT_FOUND = "user_settings.viewer_default_not_found"
    """默认设置不存在"""

    USER_SETTINGS_AVATAR_INVALID = "user_settings.avatar_invalid"
    """头像设置无效"""

    # ==================== entry ====================

    ENTRY_NOT_FOUND = "entry.not_found"
    """对象不存在"""

    ENTRY_FORBIDDEN = "entry.forbidden"
    """无权操作此对象"""

    ENTRY_VIEW_FORBIDDEN = "entry.view_forbidden"
    """无权查看此对象"""

    ENTRY_BANNED = "entry.banned"
    """对象已被封禁"""

    ENTRY_INVALID_NAME = "entry.invalid_name"
    """无效的文件/目录名"""

    ENTRY_NAME_EMPTY = "entry.name_empty"
    """名称不能为空"""

    ENTRY_NAME_SLASH = "entry.name_contains_slash"
    """名称不能包含斜杠"""

    ENTRY_DUPLICATE = "entry.duplicate_name"
    """同名对象已存在"""

    ENTRY_PARENT_NOT_FOUND = "entry.parent_not_found"
    """父目录不存在"""

    ENTRY_PARENT_NOT_DIR = "entry.parent_not_directory"
    """父对象不是目录"""

    ENTRY_TARGET_NOT_FOUND = "entry.target_not_found"
    """目标目录不存在"""

    ENTRY_TARGET_NOT_DIR = "entry.target_not_directory"
    """目标不是有效文件夹"""

    ENTRY_TARGET_BANNED = "entry.target_banned"
    """目标目录已被封禁"""

    ENTRY_ROOT_RENAME = "entry.cannot_rename_root"
    """无法重命名根目录"""

    ENTRY_ROOT_POLICY_CHANGE = "entry.cannot_change_root_policy"
    """不能对根目录切换存储策略"""

    ENTRY_SAME_POLICY = "entry.same_policy"
    """目标策略与当前策略相同"""

    ENTRY_COPY_ROOT = "entry.cannot_copy_root"
    """无法复制根目录"""

    ENTRY_NOT_DIR = "entry.not_a_directory"
    """指定路径不是目录"""

    ENTRY_METADATA_NS_FORBIDDEN = "entry.metadata_namespace_forbidden"
    """不允许修改此命名空间的元数据"""

    ENTRY_CUSTOM_PROP_DUPLICATE = "entry.custom_property_duplicate"
    """同名自定义属性已存在"""

    ENTRY_CUSTOM_PROP_FORBIDDEN = "entry.custom_property_forbidden"
    """无权操作此属性"""

    # ==================== file ====================

    FILE_NOT_FOUND = "file.not_found"
    """文件不存在"""

    FILE_NOT_FILE = "file.not_a_file"
    """对象不是文件"""

    FILE_STORAGE_PATH_MISSING = "file.storage_path_missing"
    """文件存储路径丢失"""

    FILE_PHYSICAL_NOT_FOUND = "file.physical_not_found"
    """物理文件不存在"""

    FILE_UPLOAD_SESSION_NOT_FOUND = "file.upload_session_not_found"
    """上传会话不存在"""

    FILE_UPLOAD_SESSION_EXPIRED = "file.upload_session_expired"
    """上传会话已过期"""

    FILE_UPLOAD_INVALID_CHUNK = "file.upload_invalid_chunk_index"
    """无效的分片索引"""

    FILE_QUOTA_EXCEEDED = "file.quota_exceeded"
    """存储空间不足"""

    FILE_SIZE_EXCEEDED = "file.size_exceeded"
    """文件大小超过限制"""

    FILE_NO_EXTENSION = "file.no_extension"
    """文件无扩展名"""

    FILE_NOT_UTF8 = "file.not_utf8_text"
    """文件不是有效的 UTF-8 文本"""

    FILE_CONTENT_MODIFIED = "file.content_modified"
    """文件内容已被修改（乐观锁冲突）"""

    FILE_INVALID_PATCH = "file.invalid_patch_format"
    """无效的 patch 格式"""

    FILE_PATCH_MISMATCH = "file.patch_mismatch"
    """Patch 应用失败，差异内容不匹配"""

    FILE_EXTERNAL_LINK_NOT_FOUND = "file.external_link_not_found"
    """外链不存在"""

    # ==================== directory ====================

    DIR_NOT_FOUND = "directory.not_found"
    """目录不存在"""

    DIR_DUPLICATE = "directory.duplicate_name"
    """同名目录已存在"""

    # ==================== policy ====================

    POLICY_NOT_FOUND = "policy.not_found"
    """存储策略不存在"""

    POLICY_FORBIDDEN = "policy.forbidden"
    """当前用户组无权使用该存储策略"""

    POLICY_EXTERNAL_LINK_DISABLED = "policy.external_link_disabled"
    """当前存储策略未启用外链功能"""

    POLICY_NAME_EXISTS = "policy.name_exists"
    """策略名称已存在"""

    POLICY_LOCAL_NO_PATH = "policy.local_missing_server_path"
    """本地存储策略必须指定 server 路径"""

    POLICY_DIR_CREATE_FAILED = "policy.directory_creation_failed"
    """创建存储目录失败"""

    POLICY_HAS_FILES = "policy.has_files"
    """存储策略下存在文件，无法删除"""

    # ==================== share ====================

    SHARE_NOT_FOUND = "share.not_found"
    """分享不存在"""

    SHARE_EXPIRED = "share.expired"
    """分享已过期"""

    SHARE_ENTRY_DELETED = "share.entry_deleted"
    """分享关联的文件已被删除"""

    SHARE_PASSWORD_REQUIRED = "share.password_required"
    """请输入提取码"""

    SHARE_PASSWORD_WRONG = "share.password_wrong"
    """提取码错误"""

    SHARE_FORBIDDEN = "share.forbidden"
    """无权操作此分享"""

    # ==================== admin ====================

    ADMIN_GROUP_NAME_EXISTS = "admin.group_name_exists"
    """用户组名称已存在"""

    ADMIN_GROUP_NOT_FOUND = "admin.group_not_found"
    """用户组不存在"""

    ADMIN_GROUP_DEFAULT_IMMUTABLE = "admin.default_admin_group_immutable"
    """默认管理员不允许更改用户组"""

    ADMIN_GROUP_HAS_USERS = "admin.group_has_users"
    """用户组下存在用户，无法删除"""

    ADMIN_TASK_NOT_FOUND = "admin.task_not_found"
    """任务不存在"""

    ADMIN_THEME_NAME_EXISTS = "admin.theme_name_exists"
    """主题预设名称已存在"""

    ADMIN_FILE_APP_KEY_EXISTS = "admin.file_app_key_exists"
    """应用标识已存在"""

    ADMIN_SLAVE_RESPONSE_ERROR = "admin.slave_response_error"
    """从机响应错误"""

    ADMIN_SLAVE_CONNECTION_FAILED = "admin.slave_connection_failed"
    """连接失败"""

    # ==================== webdav ====================

    WEBDAV_DISABLED = "webdav.disabled"
    """WebDAV 功能未启用"""

    WEBDAV_ACCOUNT_NAME_EXISTS = "webdav.account_name_exists"
    """账户名已存在"""

    WEBDAV_ACCOUNT_NOT_FOUND = "webdav.account_not_found"
    """WebDAV 账户不存在"""

    WEBDAV_ROOT_INVALID = "webdav.root_path_invalid"
    """根目录路径不存在或不是目录"""

    # ==================== wopi ====================

    WOPI_TOKEN_INVALID = "wopi.token_invalid"
    """WOPI token 无效或文件不匹配"""

    WOPI_WRITE_FORBIDDEN = "wopi.write_forbidden"
    """没有写入权限"""

    WOPI_NO_VIEWER = "wopi.no_viewer_available"
    """无可用的 WOPI 查看器"""

    WOPI_EDITOR_NOT_CONFIGURED = "wopi.editor_not_configured"
    """WOPI 应用未配置编辑器 URL 模板"""

    WOPI_DISCOVERY_NOT_CONFIGURED = "wopi.discovery_not_configured"
    """未配置 WOPI Discovery URL"""

    WOPI_DISCOVERY_FAILED = "wopi.discovery_failed"
    """WOPI Discovery 连接失败"""

    WOPI_APP_TYPE_MISMATCH = "wopi.app_type_not_wopi"
    """仅 WOPI 类型应用支持自动发现"""

    # ==================== captcha ====================

    CAPTCHA_REQUIRED = "captcha.required"
    """需要验证码"""

    CAPTCHA_INVALID = "captcha.invalid"
    """验证码验证失败"""

    # ==================== category ====================

    CATEGORY_NOT_CONFIGURED = "category.not_configured"
    """分类未配置扩展名"""

    # ==================== scope ====================

    SCOPE_MISSING = "scope.missing_permission"
    """缺少权限"""
