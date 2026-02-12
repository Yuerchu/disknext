from .setting import Setting, SettingsType
from utils.conf.appmeta import BackendVersion
from utils.password.pwd import Password
from loguru import logger as log

async def migration() -> None:
    """
    数据库迁移函数，初始化默认设置和用户组。

    :return: None
    """

    log.info('开始进行数据库初始化...')

    await init_default_settings()
    await init_default_policy()
    await init_default_group()
    await init_default_user()
    await init_default_theme_presets()

    log.info('数据库初始化结束')

default_settings: list[Setting] = [
    Setting(name="siteURL", value="http://localhost", type=SettingsType.BASIC),
    Setting(name="siteName", value="DiskNext", type=SettingsType.BASIC),
    Setting(name="register_enabled", value="1", type=SettingsType.REGISTER),
    Setting(name="default_group", value="", type=SettingsType.REGISTER),
    Setting(name="siteKeywords", value="网盘，网盘", type=SettingsType.BASIC),
    Setting(name="siteDes", value="DiskNext", type=SettingsType.BASIC),
    Setting(name="siteTitle", value="云星启智", type=SettingsType.BASIC),
    Setting(name="site_notice_public", value="", type=SettingsType.BASIC),
    Setting(name="site_notice_user", value="", type=SettingsType.BASIC),
    Setting(name="footer_code", value="", type=SettingsType.BASIC),
    Setting(name="tos_url", value="", type=SettingsType.BASIC),
    Setting(name="privacy_url", value="", type=SettingsType.BASIC),
    Setting(name="fromName", value="DiskNext", type=SettingsType.MAIL),
    Setting(name="mail_keepalive", value="30", type=SettingsType.MAIL),
    Setting(name="fromAdress", value="no-reply@yxqi.cn", type=SettingsType.MAIL),
    Setting(name="smtpHost", value="smtp.yxqi.cn", type=SettingsType.MAIL),
    Setting(name="smtpPort", value="25", type=SettingsType.MAIL),
    Setting(name="replyTo", value="feedback@yxqi.cn", type=SettingsType.MAIL),
    Setting(name="smtpUser", value="no-reply@yxqi.cn", type=SettingsType.MAIL),
    Setting(name="smtpPass", value="", type=SettingsType.MAIL),
    Setting(name="maxEditSize", value="4194304", type=SettingsType.FILE_EDIT),
    Setting(name="archive_timeout", value="60", type=SettingsType.TIMEOUT),
    Setting(name="download_timeout", value="60", type=SettingsType.TIMEOUT),
    Setting(name="preview_timeout", value="60", type=SettingsType.TIMEOUT),
    Setting(name="doc_preview_timeout", value="60", type=SettingsType.TIMEOUT),
    Setting(name="upload_credential_timeout", value="1800", type=SettingsType.TIMEOUT),
    Setting(name="upload_session_timeout", value="86400", type=SettingsType.TIMEOUT),
    Setting(name="slave_api_timeout", value="60", type=SettingsType.TIMEOUT),
    Setting(name="onedrive_monitor_timeout", value="600", type=SettingsType.TIMEOUT),
    Setting(name="share_download_session_timeout", value="2073600", type=SettingsType.TIMEOUT),
    Setting(name="onedrive_callback_check", value="20", type=SettingsType.TIMEOUT),
    Setting(name="aria2_call_timeout", value="5", type=SettingsType.TIMEOUT),
    Setting(name="onedrive_chunk_retries", value="1", type=SettingsType.RETRY),
    Setting(name="onedrive_source_timeout", value="1800", type=SettingsType.TIMEOUT),
    Setting(name="reset_after_upload_failed", value="0", type=SettingsType.UPLOAD),
    Setting(name="login_captcha", value="0", type=SettingsType.LOGIN),
    Setting(name="reg_captcha", value="0", type=SettingsType.LOGIN),
    Setting(name="reg_email_captcha", value="0", type=SettingsType.LOGIN),
    Setting(name="require_active", value="0", type=SettingsType.REGISTER),
    Setting(name="mail_activation_template", value="""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd"><html lang="zh-CN" xmlns="http://www.w3.org/1999/xhtml" xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:v="urn:schemas-microsoft-com:vml"><head><title>验证码</title><meta charset="UTF-8"><meta content="text/html; charset=UTF-8" http-equiv="Content-Type"><meta content="IE=edge" http-equiv="X-UA-Compatible"><meta content="telephone=no, date=no, address=no, email=no, url=no" name="format-detection"><meta content="width=device-width, initial-scale=1.0" name="viewport"><style>body { margin: 0; padding: 0; -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; background-color: #ffffff; }table { border-collapse: separate; mso-table-lspace: 0pt; mso-table-rspace: 0pt; width: 100%; }table td { border-collapse: collapse; }img { border: 0; height: auto; line-height: 100%; outline: none; text-decoration: none; -ms-interpolation-mode: bicubic; }body, table, td, p, a, li, blockquote { -ms-text-size-adjust: 100%; -webkit-text-size-adjust: 100%; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; }@media only screen and (max-width: 480px) {    .mobile-hide { display: none !important; }    .mobile-padding { padding: 20px !important; }    .content-width { width: 100% !important; max-width: 100% !important; }    h1 { font-size: 24px !important; line-height: 1.2 !important; }}</style></head><body style="margin: 0; padding: 0; background-color: #ffffff;"><table border="0" cellpadding="0" cellspacing="0" width="100%" role="presentation"><tr><td align="center" style="background-color: #ffffff; padding-top: 40px; padding-bottom: 40px;"><table align="center" border="0" cellpadding="0" cellspacing="0" class="content-width" style="max-width: 600px; width: 100%; background-color: #ffffff; border: 1px solid #ebebeb; border-radius: 12px; overflow: hidden;"><tr><td class="mobile-padding" style="padding: 40px 40px 30px 40px;"><table border="0" cellpadding="0" cellspacing="0" width="100%"><tr><td align="left"><a href="{{ site_url }}" target="_blank" style="text-decoration: none;">                                                                                {% if logo_url %}<img src="{{ logo_url }}" alt="{{ site_name }}" width="120" style="display: block; width: 120px; max-width: 100%; border: 0;">                                        {% else %}<span style="font-size: 24px; font-weight: bold; color: #333333;">{{ site_name }}</span>                                        {% endif %}</a></td></tr><tr><td height="30" style="font-size: 1px; line-height: 30px;">&nbsp;</td></tr></table><h1 style="margin: 0; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 24px; font-weight: 700; color: #141414; line-height: 32px;">                            验证您的邮箱</h1><table border="0" cellpadding="0" cellspacing="0" width="100%"><tr><td height="15" style="font-size: 1px; line-height: 15px;">&nbsp;</td></tr><tr><td style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 15px; color: #141414; line-height: 24px;">                                    感谢您注册<strong>{{ site_name }}</strong>，您的验证码是：</td></tr><tr><td height="25" style="font-size: 1px; line-height: 25px;">&nbsp;</td></tr></table><table border="0" cellpadding="0" cellspacing="0" width="100%"><tr><td align="left"><table border="0" cellpadding="0" cellspacing="0" style="background-color: #f4f7fa; border-radius: 8px;"><tr><td align="center" style="padding: 15px 30px;"><span style="font-family: 'Courier New', Courier, monospace; font-size: 32px; font-weight: 700; color: #0666eb; letter-spacing: 4px; display: block;">                                                    {{ verify_code }}</span></td></tr></table></td></tr><tr><td height="25" style="font-size: 1px; line-height: 25px;">&nbsp;</td></tr></table><table border="0" cellpadding="0" cellspacing="0" width="100%"><tr><td style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 14px; color: #555555; line-height: 22px;"><p style="margin: 0 0 10px 0;">该验证码<strong>{{ valid_minutes }} 分钟内</strong>有效。</p><p style="margin: 0 0 10px 0; color: #d32f2f;">为保障您的账户安全，请勿将验证码告诉他人。</p></td></tr></table><table border="0" cellpadding="0" cellspacing="0" width="100%"><tr><td height="30" style="font-size: 1px; line-height: 30px; border-bottom: 1px solid #eeeeee;">&nbsp;</td></tr><tr><td height="20" style="font-size: 1px; line-height: 20px;">&nbsp;</td></tr></table><table border="0" cellpadding="0" cellspacing="0" width="100%"><tr><td style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 12px; color: #999999; line-height: 18px;"><p style="margin: 0;">此邮件由系统自动发送，请勿直接回复。</p><p style="margin: 5px 0 0 0;">&copy; {{ current_year }} {{ site_name }}. 保留所有权利。</p></td></tr></table></td></tr></table><div style="display:none; white-space:nowrap; font:15px courier; line-height:0;">                &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp;                 &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp;</div></td></tr></table></body></html>""", type=SettingsType.MAIL_TEMPLATE),
    Setting(name="mail_reset_pwd_template", value="""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd"><html lang="zh-CN" xmlns="http://www.w3.org/1999/xhtml" xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:v="urn:schemas-microsoft-com:vml"><head><title>重置密码</title><meta charset="UTF-8"><meta content="text/html; charset=UTF-8" http-equiv="Content-Type"><meta content="IE=edge" http-equiv="X-UA-Compatible"><meta content="telephone=no, date=no, address=no, email=no, url=no" name="format-detection"><meta content="width=device-width, initial-scale=1.0" name="viewport"><style>body { margin: 0; padding: 0; -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; background-color: #ffffff; }table { border-collapse: separate; mso-table-lspace: 0pt; mso-table-rspace: 0pt; width: 100%; }table td { border-collapse: collapse; }img { border: 0; height: auto; line-height: 100%; outline: none; text-decoration: none; -ms-interpolation-mode: bicubic; }body, table, td, p, a, li, blockquote { -ms-text-size-adjust: 100%; -webkit-text-size-adjust: 100%; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; }@media only screen and (max-width: 480px) {    .mobile-hide { display: none !important; }    .mobile-padding { padding: 20px !important; }    .content-width { width: 100% !important; max-width: 100% !important; }    h1 { font-size: 24px !important; line-height: 1.2 !important; }}</style></head><body style="margin: 0; padding: 0; background-color: #ffffff;"><table border="0" cellpadding="0" cellspacing="0" width="100%" role="presentation"><tr><td align="center" style="background-color: #ffffff; padding-top: 40px; padding-bottom: 40px;"><table align="center" border="0" cellpadding="0" cellspacing="0" class="content-width" style="max-width: 600px; width: 100%; background-color: #ffffff; border: 1px solid #ebebeb; border-radius: 12px; overflow: hidden;"><tr><td class="mobile-padding" style="padding: 40px 40px 30px 40px;"><table border="0" cellpadding="0" cellspacing="0" width="100%"><tr><td align="left"><a href="{{ site_url }}" target="_blank" style="text-decoration: none;">                                        {% if logo_url %}<img src="{{ logo_url }}" alt="{{ site_name }}" width="120" style="display: block; width: 120px; max-width: 100%; border: 0;">                                        {% else %}<span style="font-size: 24px; font-weight: bold; color: #333333;">{{ site_name }}</span>                                        {% endif %}</a></td></tr><tr><td height="30" style="font-size: 1px; line-height: 30px;">&nbsp;</td></tr></table><h1 style="margin: 0; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 24px; font-weight: 700; color: #141414; line-height: 32px;">                            重置密码</h1><table border="0" cellpadding="0" cellspacing="0" width="100%"><tr><td height="15" style="font-size: 1px; line-height: 15px;">&nbsp;</td></tr><tr><td style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 15px; color: #141414; line-height: 24px;">                                    您正在申请重置<strong>{{ site_name }}</strong> 的登录密码。若确认是您本人操作，请使用下方验证码：</td></tr><tr><td height="25" style="font-size: 1px; line-height: 25px;">&nbsp;</td></tr></table><table border="0" cellpadding="0" cellspacing="0" width="100%"><tr><td align="left"><table border="0" cellpadding="0" cellspacing="0" style="background-color: #f4f7fa; border-radius: 8px;"><tr><td align="center" style="padding: 15px 30px;"><span style="font-family: 'Courier New', Courier, monospace; font-size: 32px; font-weight: 700; color: #0666eb; letter-spacing: 4px; display: block;">                                                    {{ verify_code }}</span></td></tr></table></td></tr><tr><td height="25" style="font-size: 1px; line-height: 25px;">&nbsp;</td></tr></table><table border="0" cellpadding="0" cellspacing="0" width="100%"><tr><td style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 14px; color: #555555; line-height: 22px;"><p style="margin: 0 0 10px 0;">该验证码<strong>{{ valid_minutes }} 分钟内</strong>有效。</p><p style="margin: 0 0 10px 0; color: #666666;">                                        如果您没有请求重置密码，请<strong>忽略此邮件</strong>，您的账户依然安全。</p></td></tr></table><table border="0" cellpadding="0" cellspacing="0" width="100%"><tr><td height="30" style="font-size: 1px; line-height: 30px; border-bottom: 1px solid #eeeeee;">&nbsp;</td></tr><tr><td height="20" style="font-size: 1px; line-height: 20px;">&nbsp;</td></tr></table><table border="0" cellpadding="0" cellspacing="0" width="100%"><tr><td style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 12px; color: #999999; line-height: 18px;"><p style="margin: 0;">此邮件由系统自动发送，请勿直接回复。</p><p style="margin: 5px 0 0 0;">&copy; {{ current_year }} {{ site_name }}. 保留所有权利。</p></td></tr></table></td></tr></table><div style="display:none; white-space:nowrap; font:15px courier; line-height:0;">                &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp;                 &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp;</div></td></tr></table></body></html>""", type=SettingsType.MAIL_TEMPLATE),
    Setting(name="forget_captcha", value="0", type=SettingsType.LOGIN),
    Setting(name=f"db_version_{BackendVersion}", value="installed", type=SettingsType.VERSION),
    Setting(name="hot_share_num", value="10", type=SettingsType.SHARE),
    Setting(name="gravatar_server", value="https://www.gravatar.com/", type=SettingsType.AVATAR),
    Setting(name="aria2_token", value="", type=SettingsType.ARIA2),
    Setting(name="aria2_rpcurl", value="", type=SettingsType.ARIA2),
    Setting(name="aria2_temp_path", value="", type=SettingsType.ARIA2),
    Setting(name="aria2_options", value="{}", type=SettingsType.ARIA2),
    Setting(name="aria2_interval", value="60", type=SettingsType.ARIA2),
    Setting(name="max_worker_num", value="10", type=SettingsType.TASK),
    Setting(name="max_parallel_transfer", value="4", type=SettingsType.TASK),
    Setting(name="secret_key", value=Password.generate(256), type=SettingsType.AUTH),
    Setting(name="temp_path", value="temp", type=SettingsType.PATH),
    Setting(name="avatar_path", value="avatar", type=SettingsType.PATH),
    Setting(name="avatar_size", value="2097152", type=SettingsType.AVATAR),
    Setting(name="avatar_size_l", value="200", type=SettingsType.AVATAR),
    Setting(name="avatar_size_m", value="130", type=SettingsType.AVATAR),
    Setting(name="avatar_size_s", value="50", type=SettingsType.AVATAR),
    Setting(name="home_view_method", value="icon", type=SettingsType.VIEW),
    Setting(name="share_view_method", value="list", type=SettingsType.VIEW),
    Setting(name="cron_garbage_collect", value="@hourly", type=SettingsType.CRON),
    Setting(name="authn_enabled", value="0", type=SettingsType.AUTHN),
    Setting(name="captcha_height", value="60", type=SettingsType.CAPTCHA),
    Setting(name="captcha_width", value="240", type=SettingsType.CAPTCHA),
    Setting(name="captcha_mode", value="3", type=SettingsType.CAPTCHA),
    Setting(name="captcha_ComplexOfNoiseText", value="0", type=SettingsType.CAPTCHA),
    Setting(name="captcha_ComplexOfNoiseDot", value="0", type=SettingsType.CAPTCHA),
    Setting(name="captcha_IsShowHollowLine", value="0", type=SettingsType.CAPTCHA),
    Setting(name="captcha_IsShowNoiseDot", value="1", type=SettingsType.CAPTCHA),
    Setting(name="captcha_IsShowNoiseText", value="0", type=SettingsType.CAPTCHA),
    Setting(name="captcha_IsShowSlimeLine", value="1", type=SettingsType.CAPTCHA),
    Setting(name="captcha_IsShowSineLine", value="0", type=SettingsType.CAPTCHA),
    Setting(name="captcha_CaptchaLen", value="6", type=SettingsType.CAPTCHA),
    Setting(name="captcha_type", value="default", type=SettingsType.CAPTCHA),
    Setting(name="captcha_ReCaptchaKey", value="", type=SettingsType.CAPTCHA),
    Setting(name="captcha_ReCaptchaSecret", value="", type=SettingsType.CAPTCHA),
    Setting(name="captcha_CloudflareKey", value="", type=SettingsType.CAPTCHA),
    Setting(name="captcha_CloudflareSecret", value="", type=SettingsType.CAPTCHA),
    Setting(name="thumb_width", value="400", type=SettingsType.THUMB),
    Setting(name="thumb_height", value="300", type=SettingsType.THUMB),
    Setting(name="pwa_small_icon", value="/static/img/favicon.ico", type=SettingsType.PWA),
    Setting(name="pwa_medium_icon", value="/static/img/logo192.png", type=SettingsType.PWA),
    Setting(name="pwa_large_icon", value="/static/img/logo512.png", type=SettingsType.PWA),
    Setting(name="pwa_display", value="standalone", type=SettingsType.PWA),
    Setting(name="pwa_theme_color", value="#000000", type=SettingsType.PWA),
    Setting(name="pwa_background_color", value="#ffffff", type=SettingsType.PWA),
    # ==================== 认证方式配置 ====================
    Setting(name="auth_email_password_enabled", value="1", type=SettingsType.AUTH),
    Setting(name="auth_phone_sms_enabled", value="0", type=SettingsType.AUTH),
    Setting(name="auth_passkey_enabled", value="0", type=SettingsType.AUTH),
    Setting(name="auth_magic_link_enabled", value="0", type=SettingsType.AUTH),
    Setting(name="auth_password_required", value="1", type=SettingsType.AUTH),
    Setting(name="auth_phone_binding_required", value="0", type=SettingsType.AUTH),
    Setting(name="auth_email_binding_required", value="1", type=SettingsType.AUTH),
    # ==================== OAuth 配置 ====================
    Setting(name="github_enabled", value="0", type=SettingsType.OAUTH),
    Setting(name="github_client_id", value="", type=SettingsType.OAUTH),
    Setting(name="github_client_secret", value="", type=SettingsType.OAUTH),
    Setting(name="qq_enabled", value="0", type=SettingsType.OAUTH),
    Setting(name="qq_client_id", value="", type=SettingsType.OAUTH),
    Setting(name="qq_client_secret", value="", type=SettingsType.OAUTH),
    # ==================== 短信服务配置（预留） ====================
    Setting(name="sms_provider", value="", type=SettingsType.MOBILE),
    Setting(name="sms_access_key", value="", type=SettingsType.MOBILE),
    Setting(name="sms_secret_key", value="", type=SettingsType.MOBILE),
]

async def init_default_settings() -> None:
    from .setting import Setting
    from .database_connection import DatabaseManager

    log.info('初始化设置...')

    async for session in DatabaseManager.get_session():
        # 检查是否已经存在版本设置
        ver = await Setting.get(
            session,
            (Setting.type == SettingsType.VERSION) & (Setting.name == f"db_version_{BackendVersion}")
        )
        if ver and ver.value == "installed":
            return

        # 批量添加默认设置
        await Setting.add(session, default_settings)

async def init_default_group() -> None:
    from .group import Group, GroupOptions
    from .policy import Policy, GroupPolicyLink
    from .setting import Setting
    from .database_connection import DatabaseManager

    log.info('初始化用户组...')

    async for session in DatabaseManager.get_session():
        # 获取默认存储策略
        default_policy = await Policy.get(session, Policy.name == "本地存储")
        default_policy_id = default_policy.id if default_policy else None

        # 未找到初始管理组时，则创建
        if not await Group.get(session, Group.name == "管理员"):
            admin_group = Group(
                name="管理员",
                max_storage=1 * 1024 * 1024 * 1024,  # 1GB
                share_enabled=True,
                web_dav_enabled=True,
                admin=True,
            )
            admin_group_id = admin_group.id  # 在 save 前保存 UUID
            await admin_group.save(session)

            await GroupOptions(
                group_id=admin_group_id,
                archive_download=True,
                archive_task=True,
                share_download=True,
                share_free=True,
                aria2=True,
                select_node=True,
                advance_delete=True,
            ).save(session)

            # 关联默认存储策略
            if default_policy_id:
                session.add(GroupPolicyLink(
                    group_id=admin_group_id,
                    policy_id=default_policy_id,
                ))
                await session.commit()

        # 未找到初始注册会员时，则创建
        if not await Group.get(session, Group.name == "注册会员"):
            member_group = Group(
                name="注册会员",
                max_storage=1 * 1024 * 1024 * 1024,  # 1GB
                share_enabled=True,
                web_dav_enabled=True,
            )
            member_group_id = member_group.id  # 在 save 前保存 UUID
            await member_group.save(session)

            await GroupOptions(
                group_id=member_group_id,
                share_download=True,
            ).save(session)

            # 关联默认存储策略
            if default_policy_id:
                session.add(GroupPolicyLink(
                    group_id=member_group_id,
                    policy_id=default_policy_id,
                ))
                await session.commit()

            # 更新 default_group 设置为注册会员组的 UUID
            default_group_setting = await Setting.get(session, Setting.name == "default_group")
            if default_group_setting:
                default_group_setting.value = str(member_group_id)
                await default_group_setting.save(session)

        # 未找到初始游客组时，则创建
        if not await Group.get(session, Group.name == "游客"):
            guest_group = Group(
                name="游客",
                share_enabled=False,
                web_dav_enabled=False,
            )
            guest_group_id = guest_group.id  # 在 save 前保存 UUID
            await guest_group.save(session)

            await GroupOptions(
                group_id=guest_group_id,
                share_download=True,
            ).save(session)

            # 游客组不关联存储策略（无法上传）

async def init_default_user() -> None:
    from .auth_identity import AuthIdentity, AuthProviderType
    from .user import User
    from .group import Group
    from .object import Object, ObjectType
    from .policy import Policy
    from .database_connection import DatabaseManager

    log.info('初始化管理员用户...')

    async for session in DatabaseManager.get_session():
        # 检查管理员用户是否存在（通过 Setting 中的 default_admin_id 判断）
        admin_id_setting = await Setting.get(
            session,
            (Setting.type == SettingsType.AUTH) & (Setting.name == "default_admin_id")
        )
        admin_user = None
        if admin_id_setting and admin_id_setting.value:
            from uuid import UUID
            admin_user = await User.get(session, User.id == UUID(admin_id_setting.value))

        if not admin_user:
            # 获取管理员组
            admin_group = await Group.get(session, Group.name == "管理员")
            if not admin_group:
                raise RuntimeError("管理员用户组不存在，无法创建管理员用户")

            # 获取默认存储策略
            default_policy = await Policy.get(session, Policy.name == "本地存储")
            if not default_policy:
                raise RuntimeError("默认存储策略不存在，无法创建管理员用户")
            default_policy_id = default_policy.id  # 在后续 save 前保存 UUID

            # 生成管理员密码
            admin_password = Password.generate(8)
            hashed_admin_password = Password.hash(admin_password)

            admin_user = User(
                email="admin@disknext.local",
                nickname="admin",
                group_id=admin_group.id,
            )
            admin_user_id = admin_user.id  # 在 save 前保存 UUID
            await admin_user.save(session)

            # 创建 AuthIdentity（邮箱密码身份）
            await AuthIdentity(
                provider=AuthProviderType.EMAIL_PASSWORD,
                identifier="admin@disknext.local",
                credential=hashed_admin_password,
                is_primary=True,
                is_verified=True,
                user_id=admin_user_id,
            ).save(session)

            # 记录默认管理员 ID 到 Setting
            await Setting(
                name="default_admin_id",
                value=str(admin_user_id),
                type=SettingsType.AUTH,
            ).save(session)

            # 为管理员创建根目录
            await Object(
                name="/",
                type=ObjectType.FOLDER,
                owner_id=admin_user_id,
                parent_id=None,
                policy_id=default_policy_id,
            ).save(session)

            log.warning('请注意，账号密码仅显示一次，请妥善保管')
            log.info(f'初始管理员邮箱: admin@disknext.local')
            log.info(f'初始管理员密码: {admin_password}')


async def init_default_policy() -> None:
    from .policy import Policy, PolicyType
    from .database_connection import DatabaseManager
    from service.storage import LocalStorageService

    log.info('初始化默认存储策略...')

    async for session in DatabaseManager.get_session():
        # 检查默认存储策略是否存在
        default_policy = await Policy.get(session, Policy.name == "本地存储")

        if not default_policy:
            local_policy = Policy(
                name="本地存储",
                type=PolicyType.LOCAL,
                server="./data",
                is_private=True,
                max_size=0,
                auto_rename=True,
                dir_name_rule="{date}/{randomkey16}",
                file_name_rule="{randomkey16}_{originname}",
            )

            local_policy = await local_policy.save(session)

            # 创建物理存储目录
            storage_service = LocalStorageService(local_policy)
            await storage_service.ensure_base_directory()

            log.info('已创建默认本地存储策略，存储目录：./data')


async def init_default_theme_presets() -> None:
    from .color import ChromaticColor, NeutralColor
    from .theme_preset import ThemePreset
    from .database_connection import DatabaseManager

    log.info('初始化默认主题预设...')

    async for session in DatabaseManager.get_session():
        # 已存在预设则跳过
        existing_count = await ThemePreset.count(session)
        if existing_count > 0:
            return

        default_preset = ThemePreset(
            name="默认主题",
            is_default=True,
            primary=ChromaticColor.GREEN,
            secondary=ChromaticColor.BLUE,
            success=ChromaticColor.GREEN,
            info=ChromaticColor.BLUE,
            warning=ChromaticColor.YELLOW,
            error=ChromaticColor.RED,
            neutral=NeutralColor.ZINC,
        )
        await default_preset.save(session)
        log.info('已创建默认主题预设')
