from enum import StrEnum
from typing import Annotated, Self
from uuid import UUID

from pydantic import AfterValidator, EmailStr, HttpUrl, model_validator
from pydantic_extra_types.color import Color
from sqlmodel import Field, col
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodel_ext import SQLModelBase, TableBaseMixin, Str128, Str255, Str2048, Text5K, Text10K

from .auth_identity import AuthProviderType


# ==================== DTO 模型（原 setting.py）====================

class AuthMethodConfig(SQLModelBase):
    """认证方式配置 DTO"""

    provider: AuthProviderType
    """提供者类型"""

    is_enabled: bool
    """是否启用"""


class SiteConfigResponse(SQLModelBase):
    """站点配置响应 DTO"""

    title: Str128 = "DiskNext"
    """网站标题"""

    site_notice: Text5K | None = None
    """网站公告"""

    logo_light: Str2048 | None = None
    """网站Logo URL"""

    logo_dark: Str2048 | None = None
    """网站Logo URL（深色模式）"""

    register_enabled: bool = True
    """是否允许注册"""

    login_captcha: bool = False
    """登录是否需要验证码"""

    reg_captcha: bool = False
    """注册是否需要验证码"""

    forget_captcha: bool = False
    """找回密码是否需要验证码"""

    captcha_type: 'CaptchaType' = "default"
    """验证码类型"""

    captcha_key: Str255 | None = None
    """验证码 public key（DEFAULT 类型时为 None）"""

    auth_methods: list[AuthMethodConfig] = []
    """可用的登录方式列表"""

    password_required: bool = True
    """注册时是否必须设置密码"""

    phone_binding_required: bool = False
    """是否强制绑定手机号"""

    email_binding_required: bool = True
    """是否强制绑定邮箱"""

    avatar_max_size: int = 2097152
    """头像文件最大字节数（默认 2MB）"""

    footer_code: Text10K | None = None
    """自定义页脚代码"""

    tos_url: Str2048 | None = None
    """服务条款 URL"""

    privacy_url: Str2048 | None = None
    """隐私政策 URL"""


# ==================== 自定义 Annotated 类型 ====================

def _validate_http_url(v: str) -> str:
    """校验 HTTP(S) URL 格式"""
    HttpUrl(v)
    return v


def _validate_optional_http_url(v: str) -> str:
    """校验可选 HTTP URL（空字符串放行）"""
    if v:
        HttpUrl(v)
    return v


def _validate_hex_color(v: str) -> str:
    """校验 CSS 颜色格式"""
    Color(v)
    return v


HttpUrlStr = Annotated[str, AfterValidator(_validate_http_url)]
"""HTTP(S) URL 字符串，存储为 str，写入时校验 URL 格式"""

OptionalUrlStr = Annotated[str, AfterValidator(_validate_optional_http_url)]
"""可选 URL 字符串，空字符串放行，非空时校验 URL 格式"""

HexColorStr = Annotated[str, AfterValidator(_validate_hex_color)]
"""CSS 颜色字符串（#rrggbb / #rgb / named color），存储为 str"""


# ==================== 枚举类型 ====================

class CaptchaType(StrEnum):
    """验证码类型"""
    DEFAULT = "default"
    """内置图片验证码"""
    GCAPTCHA = "gcaptcha"
    """Google reCAPTCHA"""
    CLOUD_FLARE_TURNSTILE = "cloudflare turnstile"
    """Cloudflare Turnstile"""


class ViewMethod(StrEnum):
    """文件列表视图模式"""
    ICON = "icon"
    LIST = "list"
    SMALL_ICON = "smallIcon"


class PWADisplayMode(StrEnum):
    """PWA 显示模式"""
    STANDALONE = "standalone"
    FULLSCREEN = "fullscreen"
    MINIMAL_UI = "minimal-ui"
    BROWSER = "browser"


# ==================== ServerConfig 基类 ====================

class ServerConfigBase(SQLModelBase):
    """ServerConfig 字段基类，利用 Pydantic 约束确保数据有效性"""

    # ==================== BASIC ====================
    site_url: HttpUrlStr = "http://localhost"
    """站点 URL"""

    site_name: str = Field(default="DiskNext", min_length=1, max_length=128)
    """站点名称"""

    site_title: str = Field(default="云星启智", max_length=128)
    """站点标题（浏览器标签页）"""

    site_keywords: str = Field(default="网盘，网盘", max_length=512)
    """SEO 关键词"""

    site_description: str = Field(default="DiskNext", max_length=1024)
    """SEO 描述"""

    site_notice_public: str = Field(default="", max_length=4096)
    """公开公告"""

    site_notice_user: str = Field(default="", max_length=4096)
    """登录用户公告"""

    footer_code: str = Field(default="", max_length=8192)
    """自定义页脚 HTML/JS"""

    tos_url: OptionalUrlStr = ""
    """服务条款 URL"""

    privacy_url: OptionalUrlStr = ""
    """隐私政策 URL"""

    logo_light: OptionalUrlStr = ""
    """亮色模式 Logo URL"""

    logo_dark: OptionalUrlStr = ""
    """暗色模式 Logo URL"""

    # ==================== REGISTER ====================
    is_register_enabled: bool = True
    """是否开放注册"""

    default_group_id: UUID | None = None
    """新用户默认用户组"""

    is_require_active: bool = False
    """注册后是否需要邮箱激活"""

    # ==================== AUTH ====================
    secret_key: str = Field(min_length=32, max_length=512)
    """JWT 签名密钥（不可为空，初始化时随机生成）"""

    is_auth_email_password_enabled: bool = True
    """邮箱密码登录"""

    is_auth_phone_sms_enabled: bool = False
    """手机短信登录"""

    is_auth_passkey_enabled: bool = False
    """Passkey/WebAuthn 登录"""

    is_auth_magic_link_enabled: bool = False
    """Magic Link 登录"""

    is_auth_password_required: bool = True
    """注册时是否必须设置密码"""

    is_auth_phone_binding_required: bool = False
    """是否强制绑定手机"""

    is_auth_email_binding_required: bool = True
    """是否强制绑定邮箱"""

    default_admin_id: UUID | None = None
    """默认管理员用户 ID"""

    # ==================== OAUTH ====================
    is_github_enabled: bool = False
    """GitHub OAuth 开关"""

    github_client_id: str = Field(default="", max_length=256)
    """GitHub OAuth Client ID"""

    github_client_secret: str = Field(default="", max_length=256)
    """GitHub OAuth Client Secret"""

    is_qq_enabled: bool = False
    """QQ OAuth 开关"""

    qq_client_id: str = Field(default="", max_length=256)
    """QQ OAuth App ID"""

    qq_client_secret: str = Field(default="", max_length=256)
    """QQ OAuth App Key"""

    # ==================== LOGIN (captcha switches) ====================
    is_login_captcha: bool = False
    """登录是否需要验证码"""

    is_reg_captcha: bool = False
    """注册是否需要验证码"""

    is_reg_email_captcha: bool = False
    """注册邮箱验证是否需要验证码"""

    is_forget_captcha: bool = False
    """找回密码是否需要验证码"""

    # ==================== CAPTCHA ====================
    captcha_type: CaptchaType = CaptchaType.DEFAULT
    """验证码类型"""

    captcha_height: int = Field(default=60, ge=20, le=500)
    """图片验证码高度（px）"""

    captcha_width: int = Field(default=240, ge=60, le=1000)
    """图片验证码宽度（px）"""

    captcha_mode: int = Field(default=3, ge=0, le=4)
    """图片验证码模式"""

    captcha_len: int = Field(default=6, ge=4, le=10)
    """验证码字符数"""

    captcha_recaptcha_key: str = Field(default="", max_length=256)
    """reCAPTCHA Site Key"""

    captcha_recaptcha_secret: str = Field(default="", max_length=256)
    """reCAPTCHA Secret Key"""

    captcha_cloudflare_key: str = Field(default="", max_length=256)
    """Cloudflare Turnstile Site Key"""

    captcha_cloudflare_secret: str = Field(default="", max_length=256)
    """Cloudflare Turnstile Secret Key"""

    is_captcha_show_hollow_line: bool = False
    """显示空心干扰线"""

    is_captcha_show_noise_dot: bool = True
    """显示噪点"""

    is_captcha_show_noise_text: bool = False
    """显示噪声文字"""

    is_captcha_show_slime_line: bool = True
    """显示波浪干扰线"""

    is_captcha_show_sine_line: bool = False
    """显示正弦干扰线"""

    captcha_complex_noise_text: int = Field(default=0, ge=0, le=10)
    """噪声文字复杂度"""

    captcha_complex_noise_dot: int = Field(default=0, ge=0, le=10)
    """噪点复杂度"""

    # ==================== AUTHN (WebAuthn/Passkey) ====================
    is_authn_enabled: bool = False
    """WebAuthn 全局开关"""

    # ==================== AVATAR ====================
    gravatar_server: HttpUrlStr = "https://www.gravatar.com/"
    """Gravatar 服务器地址"""

    avatar_size: int = Field(default=2097152, ge=0, le=20971520)
    """头像文件最大字节数（默认 2MB，上限 20MB）"""

    avatar_size_l: int = Field(default=200, ge=32, le=1024)
    """大尺寸头像边长（px）"""

    avatar_size_m: int = Field(default=130, ge=32, le=512)
    """中尺寸头像边长（px）"""

    avatar_size_s: int = Field(default=50, ge=16, le=256)
    """小尺寸头像边长（px）"""

    # ==================== MAIL ====================
    mail_from_name: str = Field(default="DiskNext", max_length=128)
    """发件人名称"""

    mail_from_address: EmailStr = "no-reply@yxqi.cn"
    """发件人邮箱"""

    smtp_host: str = Field(default="smtp.yxqi.cn", max_length=256)
    """SMTP 服务器"""

    smtp_port: int = Field(default=25, ge=1, le=65535)
    """SMTP 端口"""

    smtp_user: str = Field(default="no-reply@yxqi.cn", max_length=256)
    """SMTP 用户名"""

    smtp_pass: str = Field(default="", max_length=512)
    """SMTP 密码"""

    smtp_reply_to: EmailStr = "feedback@yxqi.cn"
    """回复地址"""

    mail_keepalive: int = Field(default=30, ge=0, le=3600)
    """SMTP 连接保活时间（秒）"""

    # ==================== MOBILE ====================
    sms_provider: str = Field(default="", max_length=64)
    """短信服务商"""

    sms_access_key: str = Field(default="", max_length=256)
    """短信 Access Key"""

    sms_secret_key: str = Field(default="", max_length=256)
    """短信 Secret Key"""

    # ==================== TIMEOUT ====================
    timeout_archive: int = Field(default=60, ge=1, le=86400)
    """打包下载超时（秒）"""

    timeout_download: int = Field(default=60, ge=1, le=86400)
    """下载超时（秒）"""

    timeout_preview: int = Field(default=60, ge=1, le=86400)
    """预览超时（秒）"""

    timeout_doc_preview: int = Field(default=60, ge=1, le=86400)
    """文档预览超时（秒）"""

    timeout_upload_credential: int = Field(default=1800, ge=60, le=86400)
    """上传凭证有效期（秒）"""

    timeout_upload_session: int = Field(default=86400, ge=60, le=604800)
    """上传会话有效期（秒，上限7天）"""

    timeout_slave_api: int = Field(default=60, ge=1, le=600)
    """从机 API 超时（秒）"""

    timeout_onedrive_monitor: int = Field(default=600, ge=60, le=86400)
    """OneDrive 监控超时（秒）"""

    timeout_share_download_session: int = Field(default=2073600, ge=60, le=8640000)
    """分享下载会话有效期（秒，默认24天）"""

    timeout_onedrive_callback_check: int = Field(default=20, ge=1, le=600)
    """OneDrive 回调检查间隔（秒）"""

    timeout_aria2_call: int = Field(default=5, ge=1, le=60)
    """Aria2 RPC 调用超时（秒）"""

    timeout_onedrive_source: int = Field(default=1800, ge=60, le=86400)
    """OneDrive 源链接有效期（秒）"""

    # ==================== RETRY ====================
    onedrive_chunk_retries: int = Field(default=1, ge=0, le=10)
    """OneDrive 分块上传重试次数"""

    # ==================== UPLOAD ====================
    is_reset_after_upload_failed: bool = False
    """上传失败后是否重置"""

    # ==================== FILE_EDIT ====================
    max_edit_size: int = Field(default=4194304, ge=0, le=104857600)
    """在线编辑文件最大字节数（默认 4MB，上限 100MB）"""

    # ==================== PATH ====================
    temp_path: str = Field(default="temp", min_length=1, max_length=512)
    """临时文件路径"""

    avatar_path: str = Field(default="avatar", min_length=1, max_length=512)
    """头像存储路径"""

    # ==================== VIEW ====================
    home_view_method: ViewMethod = ViewMethod.ICON
    """首页默认视图模式"""

    share_view_method: ViewMethod = ViewMethod.LIST
    """分享页默认视图模式"""

    # ==================== CRON ====================
    cron_garbage_collect: str = Field(default="@hourly", max_length=64)
    """垃圾回收 cron 表达式"""

    # ==================== THUMB ====================
    thumb_width: int = Field(default=400, ge=50, le=2000)
    """缩略图宽度（px）"""

    thumb_height: int = Field(default=300, ge=50, le=2000)
    """缩略图高度（px）"""

    # ==================== PWA ====================
    pwa_small_icon: str = Field(default="/static/img/favicon.ico", max_length=2048)
    """PWA 小图标"""

    pwa_medium_icon: str = Field(default="/static/img/logo192.png", max_length=2048)
    """PWA 中图标"""

    pwa_large_icon: str = Field(default="/static/img/logo512.png", max_length=2048)
    """PWA 大图标"""

    pwa_display: PWADisplayMode = PWADisplayMode.STANDALONE
    """PWA 显示模式"""

    pwa_theme_color: HexColorStr = "#000000"
    """PWA 主题色"""

    pwa_background_color: HexColorStr = "#ffffff"
    """PWA 背景色"""

    # ==================== ARIA2 ====================
    aria2_token: str = Field(default="", max_length=256)
    """Aria2 RPC Token"""

    aria2_rpcurl: OptionalUrlStr = ""
    """Aria2 RPC 地址"""

    aria2_temp_path: str = Field(default="", max_length=512)
    """Aria2 临时下载路径"""

    aria2_options: str = Field(default="{}", max_length=4096)
    """Aria2 额外选项（JSON）"""

    aria2_interval: int = Field(default=60, ge=5, le=3600)
    """Aria2 状态轮询间隔（秒）"""

    # ==================== TASK ====================
    max_worker_num: int = Field(default=10, ge=1, le=100)
    """后台任务最大工作线程数"""

    max_parallel_transfer: int = Field(default=4, ge=1, le=32)
    """最大并行传输数"""

    # ==================== SHARE ====================
    hot_share_num: int = Field(default=10, ge=0, le=100)
    """热门分享展示数量"""

    # ==================== FILE_CATEGORY ====================
    file_category_image: str = Field(
        default="jpg,jpeg,png,gif,bmp,webp,svg,ico,tiff,tif,avif,heic,heif,psd,raw",
        max_length=2048,
    )
    """图片类扩展名（逗号分隔）"""

    file_category_video: str = Field(
        default="mp4,mkv,avi,mov,wmv,flv,webm,m4v,ts,3gp,mpg,mpeg",
        max_length=2048,
    )
    """视频类扩展名（逗号分隔）"""

    file_category_audio: str = Field(
        default="mp3,wav,flac,aac,ogg,wma,m4a,opus,ape,aiff,mid,midi",
        max_length=2048,
    )
    """音频类扩展名（逗号分隔）"""

    file_category_document: str = Field(
        default="pdf,doc,docx,odt,rtf,txt,tex,epub,pages,ppt,pptx,odp,key,xls,xlsx,csv,ods,numbers,tsv,md,markdown,mdx",
        max_length=2048,
    )
    """文档类扩展名（逗号分隔）"""

    # ==================== 跨字段校验 ====================
    #
    # captcha/oauth 一致性约束已下沉到 PostgreSQL trigger
    # （见本文件末尾 _CAPTCHA_OAUTH_TRIGGER_DDL），由数据库统一兜底，
    # 避免应用层模型构造与 DB 写入两处重复校验。

    @model_validator(mode='after')
    def _validate_avatar_size_order(self) -> Self:
        """头像尺寸大小关系：L > M > S"""
        if not (self.avatar_size_l > self.avatar_size_m > self.avatar_size_s):
            raise ValueError("头像尺寸必须满足 L > M > S")
        return self


# ==================== 数据库模型 ====================

class ServerConfig(ServerConfigBase, TableBaseMixin):
    """服务器全局配置（单例行，id=1）"""

    # FK 约束在 table 子类中定义
    default_group_id: UUID | None = Field(default=None, foreign_key='group.id')
    """新用户默认用户组"""

    default_admin_id: UUID | None = Field(default=None, foreign_key='user.id')
    """默认管理员用户 ID"""

    @classmethod
    async def get_instance(cls, session: AsyncSession) -> 'ServerConfig':
        """
        获取唯一配置实例（带 Redis 缓存）。

        :param session: 数据库异步会话
        :return: ServerConfig 单例
        :raises RuntimeError: 配置未初始化
        """
        from utils.redis.server_config_cache import ServerConfigCache

        # 1. 尝试从缓存获取
        cached = await ServerConfigCache.get()
        if cached is not None:
            return cached

        # 2. 从数据库获取
        instance = await cls.get(session, col(cls.id) == 1)
        if instance is None:
            raise RuntimeError("ServerConfig 未初始化，请先执行数据库迁移")

        # 3. 写入缓存
        await ServerConfigCache.set(instance)
        return instance

    def get_rp_config(self) -> tuple[str, str, str]:
        """
        获取 WebAuthn RP 配置。

        :return: ``(rp_id, rp_name, origin)`` 元组

        - ``rp_id``: 站点域名（从 site_url 解析，如 ``example.com``）
        - ``rp_name``: 站点标题
        - ``origin``: 完整 origin（如 ``https://example.com``）
        """
        from urllib.parse import urlparse

        site_url: str = self.site_url
        rp_name: str = self.site_title

        parsed = urlparse(site_url)
        rp_id: str = parsed.hostname or "localhost"
        origin: str = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else site_url

        return rp_id, rp_name, origin


# ==================== 更新请求 DTO ====================

class ServerConfigUpdateRequest(ServerConfigBase, all_fields_optional=True):
    """管理员更新请求（所有字段可选，仅传入需要修改的字段）

    captcha/oauth 一致性由 PostgreSQL trigger 在 UPDATE 时强制校验，
    DTO 层不再做重复检查。
    """

    @model_validator(mode='after')
    def _validate_avatar_size_order(self) -> Self:
        """仅当三个尺寸都传入时才校验大小关系"""
        if (
            self.avatar_size_l is not None
            and self.avatar_size_m is not None
            and self.avatar_size_s is not None
        ):
            if not (self.avatar_size_l > self.avatar_size_m > self.avatar_size_s):
                raise ValueError("头像尺寸必须满足 L > M > S")
        return self
