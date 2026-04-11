from loguru import logger as log
from sqlmodel import col

from utils.password.pwd import Password


async def migration() -> None:
    """
    数据库迁移函数，初始化默认数据。

    :return: None
    """

    log.info('开始进行数据库初始化...')

    await _ensure_server_config()
    await _ensure_mail_templates()
    await init_default_policy()
    await init_default_group()
    await init_default_user()
    await init_default_theme_presets()
    await init_default_file_apps()

    log.info('数据库初始化结束')

async def _ensure_server_config() -> None:
    """创建默认 ServerConfig（如不存在）"""
    from .server_config import ServerConfig
    from .database_connection import DatabaseManager

    log.info('初始化服务器配置...')

    async for session in DatabaseManager.get_session():
        existing = await ServerConfig.get(session, col(ServerConfig.id) == 1)
        if existing is not None:
            log.info(f"服务器配置已存在: id={existing.id}")
            return

        config = ServerConfig(id=1, secret_key=Password.generate(256))
        config = await config.save(session)
        log.info(f"默认服务器配置已创建: id={config.id}")


async def _ensure_mail_templates() -> None:
    """创建默认邮件模板（如不存在）"""
    from .mail_template import MailTemplate, MailTemplateType
    from .database_connection import DatabaseManager

    log.info('初始化邮件模板...')

    async for session in DatabaseManager.get_session():
        existing = await MailTemplate.get(session, fetch_mode="all")
        if existing:
            log.info(f"邮件模板已存在: {len(existing)} 个")
            return

        activation_template = MailTemplate(
            type=MailTemplateType.ACTIVATION,
            content=_DEFAULT_MAIL_ACTIVATION_TEMPLATE,
        )
        await activation_template.save(session)

        reset_template = MailTemplate(
            type=MailTemplateType.RESET_PASSWORD,
            content=_DEFAULT_MAIL_RESET_PWD_TEMPLATE,
        )
        await reset_template.save(session)
        log.info("默认邮件模板已创建")


_DEFAULT_MAIL_ACTIVATION_TEMPLATE = '''<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd"><html lang="zh-CN" xmlns="http://www.w3.org/1999/xhtml" xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:v="urn:schemas-microsoft-com:vml"><head><title>验证码</title><meta charset="UTF-8"><meta content="text/html; charset=UTF-8" http-equiv="Content-Type"><meta content="IE=edge" http-equiv="X-UA-Compatible"><meta content="telephone=no, date=no, address=no, email=no, url=no" name="format-detection"><meta content="width=device-width, initial-scale=1.0" name="viewport"><style>body { margin: 0; padding: 0; -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; background-color: #ffffff; }table { border-collapse: separate; mso-table-lspace: 0pt; mso-table-rspace: 0pt; width: 100%; }table td { border-collapse: collapse; }img { border: 0; height: auto; line-height: 100%; outline: none; text-decoration: none; -ms-interpolation-mode: bicubic; }body, table, td, p, a, li, blockquote { -ms-text-size-adjust: 100%; -webkit-text-size-adjust: 100%; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; }@media only screen and (max-width: 480px) {    .mobile-hide { display: none !important; }    .mobile-padding { padding: 20px !important; }    .content-width { width: 100% !important; max-width: 100% !important; }    h1 { font-size: 24px !important; line-height: 1.2 !important; }}</style></head><body style="margin: 0; padding: 0; background-color: #ffffff;"><table border="0" cellpadding="0" cellspacing="0" width="100%" role="presentation"><tr><td align="center" style="background-color: #ffffff; padding-top: 40px; padding-bottom: 40px;"><table align="center" border="0" cellpadding="0" cellspacing="0" class="content-width" style="max-width: 600px; width: 100%; background-color: #ffffff; border: 1px solid #ebebeb; border-radius: 12px; overflow: hidden;"><tr><td class="mobile-padding" style="padding: 40px 40px 30px 40px;"><table border="0" cellpadding="0" cellspacing="0" width="100%"><tr><td align="left"><a href="{{ site_url }}" target="_blank" style="text-decoration: none;">{% if logo_url %}<img src="{{ logo_url }}" alt="{{ site_name }}" width="120" style="display: block; width: 120px; max-width: 100%; border: 0;">{% else %}<span style="font-size: 24px; font-weight: bold; color: #333333;">{{ site_name }}</span>{% endif %}</a></td></tr><tr><td height="30" style="font-size: 1px; line-height: 30px;">&nbsp;</td></tr></table><h1 style="margin: 0; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 24px; font-weight: 700; color: #141414; line-height: 32px;">验证您的邮箱</h1><table border="0" cellpadding="0" cellspacing="0" width="100%"><tr><td height="15" style="font-size: 1px; line-height: 15px;">&nbsp;</td></tr><tr><td style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 15px; color: #141414; line-height: 24px;">感谢您注册<strong>{{ site_name }}</strong>，您的验证码是：</td></tr><tr><td height="25" style="font-size: 1px; line-height: 25px;">&nbsp;</td></tr></table><table border="0" cellpadding="0" cellspacing="0" width="100%"><tr><td align="left"><table border="0" cellpadding="0" cellspacing="0" style="background-color: #f4f7fa; border-radius: 8px;"><tr><td align="center" style="padding: 15px 30px;"><span style="font-family: 'Courier New', Courier, monospace; font-size: 32px; font-weight: 700; color: #0666eb; letter-spacing: 4px; display: block;">{{ verify_code }}</span></td></tr></table></td></tr><tr><td height="25" style="font-size: 1px; line-height: 25px;">&nbsp;</td></tr></table><table border="0" cellpadding="0" cellspacing="0" width="100%"><tr><td style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 14px; color: #555555; line-height: 22px;"><p style="margin: 0 0 10px 0;">该验证码<strong>{{ valid_minutes }} 分钟内</strong>有效。</p><p style="margin: 0 0 10px 0; color: #d32f2f;">为保障您的账户安全，请勿将验证码告诉他人。</p></td></tr></table><table border="0" cellpadding="0" cellspacing="0" width="100%"><tr><td height="30" style="font-size: 1px; line-height: 30px; border-bottom: 1px solid #eeeeee;">&nbsp;</td></tr><tr><td height="20" style="font-size: 1px; line-height: 20px;">&nbsp;</td></tr></table><table border="0" cellpadding="0" cellspacing="0" width="100%"><tr><td style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 12px; color: #999999; line-height: 18px;"><p style="margin: 0;">此邮件由系统自动发送，请勿直接回复。</p><p style="margin: 5px 0 0 0;">&copy; {{ current_year }} {{ site_name }}. 保留所有权利。</p></td></tr></table></td></tr></table></td></tr></table></body></html>'''

_DEFAULT_MAIL_RESET_PWD_TEMPLATE = '''<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd"><html lang="zh-CN" xmlns="http://www.w3.org/1999/xhtml" xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:v="urn:schemas-microsoft-com:vml"><head><title>重置密码</title><meta charset="UTF-8"><meta content="text/html; charset=UTF-8" http-equiv="Content-Type"><meta content="IE=edge" http-equiv="X-UA-Compatible"><meta content="telephone=no, date=no, address=no, email=no, url=no" name="format-detection"><meta content="width=device-width, initial-scale=1.0" name="viewport"><style>body { margin: 0; padding: 0; -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; background-color: #ffffff; }table { border-collapse: separate; mso-table-lspace: 0pt; mso-table-rspace: 0pt; width: 100%; }table td { border-collapse: collapse; }img { border: 0; height: auto; line-height: 100%; outline: none; text-decoration: none; -ms-interpolation-mode: bicubic; }body, table, td, p, a, li, blockquote { -ms-text-size-adjust: 100%; -webkit-text-size-adjust: 100%; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; }@media only screen and (max-width: 480px) {    .mobile-hide { display: none !important; }    .mobile-padding { padding: 20px !important; }    .content-width { width: 100% !important; max-width: 100% !important; }    h1 { font-size: 24px !important; line-height: 1.2 !important; }}</style></head><body style="margin: 0; padding: 0; background-color: #ffffff;"><table border="0" cellpadding="0" cellspacing="0" width="100%" role="presentation"><tr><td align="center" style="background-color: #ffffff; padding-top: 40px; padding-bottom: 40px;"><table align="center" border="0" cellpadding="0" cellspacing="0" class="content-width" style="max-width: 600px; width: 100%; background-color: #ffffff; border: 1px solid #ebebeb; border-radius: 12px; overflow: hidden;"><tr><td class="mobile-padding" style="padding: 40px 40px 30px 40px;"><table border="0" cellpadding="0" cellspacing="0" width="100%"><tr><td align="left"><a href="{{ site_url }}" target="_blank" style="text-decoration: none;">{% if logo_url %}<img src="{{ logo_url }}" alt="{{ site_name }}" width="120" style="display: block; width: 120px; max-width: 100%; border: 0;">{% else %}<span style="font-size: 24px; font-weight: bold; color: #333333;">{{ site_name }}</span>{% endif %}</a></td></tr><tr><td height="30" style="font-size: 1px; line-height: 30px;">&nbsp;</td></tr></table><h1 style="margin: 0; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 24px; font-weight: 700; color: #141414; line-height: 32px;">重置密码</h1><table border="0" cellpadding="0" cellspacing="0" width="100%"><tr><td height="15" style="font-size: 1px; line-height: 15px;">&nbsp;</td></tr><tr><td style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 15px; color: #141414; line-height: 24px;">您正在申请重置<strong>{{ site_name }}</strong> 的登录密码。若确认是您本人操作，请使用下方验证码：</td></tr><tr><td height="25" style="font-size: 1px; line-height: 25px;">&nbsp;</td></tr></table><table border="0" cellpadding="0" cellspacing="0" width="100%"><tr><td align="left"><table border="0" cellpadding="0" cellspacing="0" style="background-color: #f4f7fa; border-radius: 8px;"><tr><td align="center" style="padding: 15px 30px;"><span style="font-family: 'Courier New', Courier, monospace; font-size: 32px; font-weight: 700; color: #0666eb; letter-spacing: 4px; display: block;">{{ verify_code }}</span></td></tr></table></td></tr><tr><td height="25" style="font-size: 1px; line-height: 25px;">&nbsp;</td></tr></table><table border="0" cellpadding="0" cellspacing="0" width="100%"><tr><td style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 14px; color: #555555; line-height: 22px;"><p style="margin: 0 0 10px 0;">该验证码<strong>{{ valid_minutes }} 分钟内</strong>有效。</p><p style="margin: 0 0 10px 0; color: #666666;">如果您没有请求重置密码，请<strong>忽略此邮件</strong>，您的账户依然安全。</p></td></tr></table><table border="0" cellpadding="0" cellspacing="0" width="100%"><tr><td height="30" style="font-size: 1px; line-height: 30px; border-bottom: 1px solid #eeeeee;">&nbsp;</td></tr><tr><td height="20" style="font-size: 1px; line-height: 20px;">&nbsp;</td></tr></table><table border="0" cellpadding="0" cellspacing="0" width="100%"><tr><td style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 12px; color: #999999; line-height: 18px;"><p style="margin: 0;">此邮件由系统自动发送，请勿直接回复。</p><p style="margin: 5px 0 0 0;">&copy; {{ current_year }} {{ site_name }}. 保留所有权利。</p></td></tr></table></td></tr></table></td></tr></table></body></html>'''

async def init_default_group() -> None:
    from .group import Group, GroupOptions
    from .policy import Policy, GroupPolicyLink
    from .server_config import ServerConfig
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
            admin_group = await admin_group.save(session)

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
            member_group = await member_group.save(session)

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

            # 更新 ServerConfig 的 default_group_id
            config = await ServerConfig.get(session, col(ServerConfig.id) == 1)
            if config:
                config.default_group_id = member_group_id
                config = await config.save(session)

        # 未找到初始游客组时，则创建
        if not await Group.get(session, Group.name == "游客"):
            guest_group = Group(
                name="游客",
                share_enabled=False,
                web_dav_enabled=False,
            )
            guest_group_id = guest_group.id  # 在 save 前保存 UUID
            guest_group = await guest_group.save(session)

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
    from .server_config import ServerConfig
    from .database_connection import DatabaseManager

    log.info('初始化管理员用户...')

    async for session in DatabaseManager.get_session():
        # 检查管理员用户是否存在（通过 ServerConfig.default_admin_id 判断）
        config = await ServerConfig.get(session, col(ServerConfig.id) == 1)
        admin_user = None
        if config and config.default_admin_id:
            admin_user = await User.get(session, User.id == config.default_admin_id)

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
            admin_user = await admin_user.save(session)

            # 创建 AuthIdentity（邮箱密码身份）
            await AuthIdentity(
                provider=AuthProviderType.EMAIL_PASSWORD,
                identifier="admin@disknext.local",
                credential=hashed_admin_password,
                is_primary=True,
                is_verified=True,
                user_id=admin_user_id,
            ).save(session)

            # 记录默认管理员 ID 到 ServerConfig
            config = await ServerConfig.get(session, col(ServerConfig.id) == 1)
            if config:
                config.default_admin_id = admin_user_id
                config = await config.save(session)

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
    from utils.storage import LocalStorageService

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
        default_preset = await default_preset.save(session)
        log.info('已创建默认主题预设')


# ==================== 默认文件查看器应用种子数据 ====================

_DEFAULT_FILE_APPS: list[dict] = [
    # 内置应用（type=builtin，默认启用）
    {
        "name": "PDF 阅读器",
        "app_key": "pdfjs",
        "type": "builtin",
        "icon": "file-pdf",
        "description": "基于 pdf.js 的 PDF 在线阅读器",
        "is_enabled": True,
        "extensions": ["pdf"],
    },
    {
        "name": "代码编辑器",
        "app_key": "monaco",
        "type": "builtin",
        "icon": "code",
        "description": "基于 Monaco Editor 的代码编辑器",
        "is_enabled": True,
        "extensions": [
            "txt", "md", "json", "xml", "yaml", "yml",
            "py", "js", "ts", "jsx", "tsx",
            "html", "css", "scss", "less",
            "sh", "bash", "zsh",
            "c", "cpp", "h", "hpp",
            "java", "kt", "go", "rs", "rb",
            "sql", "graphql",
            "toml", "ini", "cfg", "conf",
            "env", "gitignore", "dockerfile",
            "vue", "svelte",
        ],
    },
    {
        "name": "Markdown 预览",
        "app_key": "markdown",
        "type": "builtin",
        "icon": "markdown",
        "description": "Markdown 实时预览",
        "is_enabled": True,
        "extensions": ["md", "markdown", "mdx"],
    },
    {
        "name": "图片查看器",
        "app_key": "image_viewer",
        "type": "builtin",
        "icon": "image",
        "description": "图片在线查看器",
        "is_enabled": True,
        "extensions": ["jpg", "jpeg", "png", "gif", "bmp", "webp", "svg", "ico", "avif"],
    },
    {
        "name": "视频播放器",
        "app_key": "video_player",
        "type": "builtin",
        "icon": "video",
        "description": "HTML5 视频播放器",
        "is_enabled": True,
        "extensions": ["mp4", "webm", "ogg", "mov", "mkv", "m3u8"],
    },
    {
        "name": "音频播放器",
        "app_key": "audio_player",
        "type": "builtin",
        "icon": "audio",
        "description": "HTML5 音频播放器",
        "is_enabled": True,
        "extensions": ["mp3", "wav", "ogg", "flac", "aac", "m4a", "opus"],
    },
    {
        "name": "EPUB 阅读器",
        "app_key": "epub_reader",
        "type": "builtin",
        "icon": "book-open",
        "description": "阅读 EPUB 电子书",
        "is_enabled": True,
        "extensions": ["epub"],
    },
    {
        "name": "3D 模型预览",
        "app_key": "model_viewer",
        "type": "builtin",
        "icon": "cube",
        "description": "预览 3D 模型",
        "is_enabled": True,
        "extensions": ["gltf", "glb", "stl", "obj", "fbx", "ply", "3mf"],
    },
    {
        "name": "Font Viewer",
        "app_key": "font_viewer",
        "type": "builtin",
        "icon": "type",
        "description": "预览字体文件并显示元数据和文本样本",
        "is_enabled": True,
        "extensions": ["ttf", "otf", "woff", "woff2"],
    },
    {
        "name": "Office 在线预览",
        "app_key": "office_viewer",
        "type": "iframe",
        "icon": "file-word",
        "description": "使用 Microsoft Office Online 预览文档",
        "is_enabled": True,
        "iframe_url_template": "https://view.officeapps.live.com/op/embed.aspx?src={file_url}",
        "extensions": ["doc", "docx", "xls", "xlsx", "ppt", "pptx"],
    },
]


async def init_default_file_apps() -> None:
    """初始化默认文件查看器应用"""
    from .file_app import FileApp, FileAppExtension, FileAppType
    from .database_connection import DatabaseManager

    log.info('初始化文件查看器应用...')

    async for session in DatabaseManager.get_session():
        # 已存在应用则跳过
        existing_count = await FileApp.count(session)
        if existing_count > 0:
            return

        for app_data in _DEFAULT_FILE_APPS:
            extensions = app_data["extensions"]

            app = FileApp(
                name=app_data["name"],
                app_key=app_data["app_key"],
                type=FileAppType(app_data["type"]),
                icon=app_data.get("icon"),
                description=app_data.get("description"),
                is_enabled=app_data.get("is_enabled", True),
                iframe_url_template=app_data.get("iframe_url_template"),
                wopi_discovery_url=app_data.get("wopi_discovery_url"),
                wopi_editor_url_template=app_data.get("wopi_editor_url_template"),
            )
            app = await app.save(session)
            app_id = app.id

            for i, ext in enumerate(extensions):
                ext_record = FileAppExtension(
                    app_id=app_id,
                    extension=ext.lower(),
                    priority=i,
                )
                ext_record = await ext_record.save(session)

        log.info(f'已创建 {len(_DEFAULT_FILE_APPS)} 个默认文件查看器应用')
