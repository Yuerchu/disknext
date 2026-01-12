
from .setting import Setting, SettingsType
from .color import ThemeResponse
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

    log.info('数据库初始化结束')

default_settings: list[Setting] = [
    Setting(name="siteURL", value="http://localhost", type=SettingsType.BASIC),
    Setting(name="siteName", value="DiskNext", type=SettingsType.BASIC),
    Setting(name="register_enabled", value="1", type=SettingsType.REGISTER),
    Setting(name="default_group", value="", type=SettingsType.REGISTER),  # UUID 在组创建后更新
    Setting(name="siteKeywords", value="网盘，网盘", type=SettingsType.BASIC),
    Setting(name="siteDes", value="DiskNext", type=SettingsType.BASIC),
    Setting(name="siteTitle", value="云星启智", type=SettingsType.BASIC),
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
    Setting(name="email_active", value="0", type=SettingsType.REGISTER),
    Setting(name="mail_activation_template", value="""<!DOCTYPE html PUBLIC"-//W3C//DTD XHTML 1.0 Transitional//EN""http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd"><html xmlns="http://www.w3.org/1999/xhtml"style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; box-sizing: border-box; 
font-size: 14px; margin: 0;"><head><meta name="viewport"content="width=device-width"/><meta http-equiv="Content-Type"content="text/html; charset=UTF-8"/><title>激活您的账户</title><style type="text/css">img{max-width:100%}body{-webkit-font-smoothing:antialiased;-webkit-text-size-adjust:none;width:100%!important;height:100%;line-height:1.6em}body{background-color:#f6f6f6}@media only screen and(max-width:640px){body{padding:0!important}h1{font-weight:800!important;margin:20px 0 5px!important}h2{font-weight:800!important;margin:20px 0 5px!important}h3{font-weight:800!important;margin:20px 0 5px!important}h4{font-weight:800!important;margin:20px 0 5px!important}h1{font-size:22px!important}h2{font-size:18px!important}h3{font-size:16px!important}.container{padding:0!important;width:100%!important}.content{padding:0!important}.content-wrap{padding:10px!important}.invoice{width:100%!important}}</style></head><body itemscope itemtype="http://schema.org/EmailMessage"style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: 
border-box; font-size: 14px; -webkit-font-smoothing: antialiased; -webkit-text-size-adjust: none; width: 100% !important; height: 100%; line-height: 1.6em; background-color: #f6f6f6; margin: 0;"bgcolor="#f6f6f6"><table class="body-wrap"style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; width: 100%; background-color: #f6f6f6; margin: 0;"bgcolor="#f6f6f6"><tr style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; 
box-sizing: border-box; font-size: 14px; margin: 0;"><td style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; vertical-align: top; margin: 0;"valign="top"></td><td class="container"width="600"style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; vertical-align: top; display: block !important; max-width: 600px !important; clear: both !important; margin: 0 auto;"valign="top"><div class="content"style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; max-width: 600px; display: block; margin: 0 auto; padding: 20px;"><table class="main"width="100%"cellpadding="0"cellspacing="0"style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; border-radius: 3px; background-color: #fff; margin: 0; border: 1px 
solid #e9e9e9;"bgcolor="#fff"><tr style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 
14px; margin: 0;"><td class="alert alert-warning"style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 16px; vertical-align: top; color: #fff; font-weight: 500; text-align: center; border-radius: 3px 3px 0 0; background-color: #009688; margin: 0; padding: 20px;"align="center"bgcolor="#FF9F00"valign="top">激活{siteTitle}账户</td></tr><tr style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; margin: 0;"><td class="content-wrap"style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; vertical-align: top; margin: 0; padding: 20px;"valign="top"><table width="100%"cellpadding="0"cellspacing="0"style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; margin: 0;"><tr style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; margin: 0;"><td class="content-block"style="font-family: 'Helvetica 
Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; vertical-align: top; margin: 0; padding: 0 0 20px;"valign="top">亲爱的<strong style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; margin: 0;">{userName}</strong>：</td></tr><tr style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; margin: 0;"><td class="content-block"style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; vertical-align: top; margin: 0; padding: 0 0 20px;"valign="top">感谢您注册{siteTitle},请点击下方按钮完成账户激活。</td></tr><tr style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; margin: 0;"><td class="content-block"style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; vertical-align: top; margin: 0; padding: 0 0 20px;"valign="top"><a href="{activationUrl}"class="btn-primary"style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; color: #FFF; text-decoration: none; line-height: 2em; font-weight: bold; text-align: center; cursor: pointer; display: inline-block; border-radius: 5px; text-transform: capitalize; background-color: #009688; margin: 0; border-color: #009688; border-style: solid; border-width: 10px 20px;">激活账户</a></td></tr><tr style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; margin: 0;"><td class="content-block"style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; vertical-align: top; margin: 0; padding: 0 0 20px;"valign="top">感谢您选择{siteTitle}。</td></tr></table></td></tr></table><div class="footer"style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; width: 100%; clear: both; color: #999; margin: 0; padding: 20px;"><table width="100%"style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; margin: 0;"><tr style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; margin: 0;"><td class="aligncenter content-block"style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 12px; vertical-align: top; color: #999; text-align: center; margin: 0; padding: 0 0 20px;"align="center"valign="top">此邮件由系统自动发送，请不要直接回复。</td></tr></table></div></div></td><td style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; vertical-align: top; margin: 0;"valign="top"></td></tr></table></body></html>""", type=SettingsType.MAIL_TEMPLATE),
    Setting(name="forget_captcha", value="0", type=SettingsType.LOGIN),
    Setting(name="mail_reset_pwd_template", value="""<!DOCTYPE html PUBLIC"-//W3C//DTD XHTML 1.0 Transitional//EN""http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd"><html xmlns="http://www.w3.org/1999/xhtml"style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; box-sizing: border-box; 
font-size: 14px; margin: 0;"><head><meta name="viewport"content="width=device-width"/><meta http-equiv="Content-Type"content="text/html; charset=UTF-8"/><title>重设密码</title><style type="text/css">img{max-width:100%}body{-webkit-font-smoothing:antialiased;-webkit-text-size-adjust:none;width:100%!important;height:100%;line-height:1.6em}body{background-color:#f6f6f6}@media only screen and(max-width:640px){body{padding:0!important}h1{font-weight:800!important;margin:20px 0 5px!important}h2{font-weight:800!important;margin:20px 0 5px!important}h3{font-weight:800!important;margin:20px 0 5px!important}h4{font-weight:800!important;margin:20px 0 5px!important}h1{font-size:22px!important}h2{font-size:18px!important}h3{font-size:16px!important}.container{padding:0!important;width:100%!important}.content{padding:0!important}.content-wrap{padding:10px!important}.invoice{width:100%!important}}</style></head><body itemscope itemtype="http://schema.org/EmailMessage"style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: 
border-box; font-size: 14px; -webkit-font-smoothing: antialiased; -webkit-text-size-adjust: none; width: 100% !important; height: 100%; line-height: 1.6em; background-color: #f6f6f6; margin: 0;"bgcolor="#f6f6f6"><table class="body-wrap"style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; width: 100%; background-color: #f6f6f6; margin: 0;"bgcolor="#f6f6f6"><tr style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; 
box-sizing: border-box; font-size: 14px; margin: 0;"><td style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; vertical-align: top; margin: 0;"valign="top"></td><td class="container"width="600"style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; vertical-align: top; display: block !important; max-width: 600px !important; clear: both !important; margin: 0 auto;"valign="top"><div class="content"style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; max-width: 600px; display: block; margin: 0 auto; padding: 20px;"><table class="main"width="100%"cellpadding="0"cellspacing="0"style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; border-radius: 3px; background-color: #fff; margin: 0; border: 1px 
solid #e9e9e9;"bgcolor="#fff"><tr style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 
14px; margin: 0;"><td class="alert alert-warning"style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 16px; vertical-align: top; color: #fff; font-weight: 500; text-align: center; border-radius: 3px 3px 0 0; background-color: #2196F3; margin: 0; padding: 20px;"align="center"bgcolor="#FF9F00"valign="top">重设{siteTitle}密码</td></tr><tr style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; margin: 0;"><td class="content-wrap"style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; vertical-align: top; margin: 0; padding: 20px;"valign="top"><table width="100%"cellpadding="0"cellspacing="0"style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; margin: 0;"><tr style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; margin: 0;"><td class="content-block"style="font-family: 'Helvetica 
Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; vertical-align: top; margin: 0; padding: 0 0 20px;"valign="top">亲爱的<strong style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; margin: 0;">{userName}</strong>：</td></tr><tr style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; margin: 0;"><td class="content-block"style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; vertical-align: top; margin: 0; padding: 0 0 20px;"valign="top">请点击下方按钮完成密码重设。如果非你本人操作，请忽略此邮件。</td></tr><tr style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; margin: 0;"><td class="content-block"style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; vertical-align: top; margin: 0; padding: 0 0 20px;"valign="top"><a href="{resetUrl}"class="btn-primary"style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; color: #FFF; text-decoration: none; line-height: 2em; font-weight: bold; text-align: center; cursor: pointer; display: inline-block; border-radius: 5px; text-transform: capitalize; background-color: #2196F3; margin: 0; border-color: #2196F3; border-style: solid; border-width: 10px 20px;">重设密码</a></td></tr><tr style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; margin: 0;"><td class="content-block"style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; vertical-align: top; margin: 0; padding: 0 0 20px;"valign="top">感谢您选择{siteTitle}。</td></tr></table></td></tr></table><div class="footer"style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; width: 100%; clear: both; color: #999; margin: 0; padding: 20px;"><table width="100%"style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; margin: 0;"><tr style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; margin: 0;"><td class="aligncenter content-block"style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 12px; vertical-align: top; color: #999; text-align: center; margin: 0; padding: 0 0 20px;"align="center"valign="top">此邮件由系统自动发送，请不要直接回复。</td></tr></table></div></div></td><td style="font-family: 'Helvetica Neue',Helvetica,Arial,sans-serif; box-sizing: border-box; font-size: 14px; vertical-align: top; margin: 0;"valign="top"></td></tr></table></body></html>""", type=SettingsType.MAIL_TEMPLATE),
    Setting(name=f"db_version_{BackendVersion}", value="installed", type=SettingsType.VERSION),
    Setting(name="hot_share_num", value="10", type=SettingsType.SHARE),
    Setting(name="gravatar_server", value="https://www.gravatar.com/", type=SettingsType.AVATAR),
    Setting(name="defaultTheme", value="#3f51b5", type=SettingsType.BASIC),
    Setting(name="themes", value=ThemeResponse().model_dump_json(), type=SettingsType.BASIC),
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
    Setting(name="captcha_IsUseReCaptcha", value="0", type=SettingsType.CAPTCHA),
    Setting(name="captcha_ReCaptchaKey", value="defaultKey", type=SettingsType.CAPTCHA),
    Setting(name="captcha_ReCaptchaSecret", value="defaultSecret", type=SettingsType.CAPTCHA),
    Setting(name="thumb_width", value="400", type=SettingsType.THUMB),
    Setting(name="thumb_height", value="300", type=SettingsType.THUMB),
    Setting(name="pwa_small_icon", value="/static/img/favicon.ico", type=SettingsType.PWA),
    Setting(name="pwa_medium_icon", value="/static/img/logo192.png", type=SettingsType.PWA),
    Setting(name="pwa_large_icon", value="/static/img/logo512.png", type=SettingsType.PWA),
    Setting(name="pwa_display", value="standalone", type=SettingsType.PWA),
    Setting(name="pwa_theme_color", value="#000000", type=SettingsType.PWA),
    Setting(name="pwa_background_color", value="#ffffff", type=SettingsType.PWA),
]

async def init_default_settings() -> None:
    from .setting import Setting
    from .database import get_session

    log.info('初始化设置...')

    async for session in get_session():
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
    from .database import get_session

    log.info('初始化用户组...')

    async for session in get_session():
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
    from .user import User
    from .group import Group
    from .object import Object, ObjectType
    from .policy import Policy
    from .database import get_session

    log.info('初始化管理员用户...')

    async for session in get_session():
        # 检查管理员用户是否存在
        admin_user = await User.get(session, User.username == "admin")

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
                username="admin",
                nickname="admin",
                group_id=admin_group.id,
                password=hashed_admin_password,
            )
            admin_user_id = admin_user.id  # 在 save 前保存 UUID
            admin_username = admin_user.username
            await admin_user.save(session)

            # 为管理员创建根目录（使用用户名作为目录名）
            await Object(
                name=admin_username,
                type=ObjectType.FOLDER,
                owner_id=admin_user_id,
                parent_id=None,
                policy_id=default_policy_id,
            ).save(session)

            log.warning('请注意，账号密码仅显示一次，请妥善保管')
            log.info(f'初始管理员账号: admin')
            log.info(f'初始管理员密码: {admin_password}')


async def init_default_policy() -> None:
    from .policy import Policy, PolicyType
    from .database import get_session
    from service.storage import LocalStorageService

    log.info('初始化默认存储策略...')

    async for session in get_session():
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