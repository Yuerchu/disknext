"""
邮件发送服务

提供异步 SMTP 发送，支持 Jinja2 模板渲染、连接复用和空闲自动断开。
"""
import asyncio
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import ClassVar

import aiosmtplib
from jinja2 import Template
from loguru import logger as l
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel_ext import cond

from sqlmodels.mail_template import MailTemplate, MailTemplateType, SmtpEncryption
from sqlmodels.server_config import ServerConfig
from utils import http_exceptions
from utils.http.error_codes import ErrorCode as E


class MailService:
    """
    邮件发送服务，纯 classmethod 单例。

    连接在首次发送时懒初始化，空闲超过 mail_keepalive 秒后自动断开。
    """

    _client: ClassVar[aiosmtplib.SMTP | None] = None
    _lock: ClassVar[asyncio.Lock | None] = None
    _idle_task: ClassVar[asyncio.Task[None] | None] = None

    def __new__(cls, *args: object, **kwargs: object) -> 'MailService':
        raise RuntimeError(f"{cls.__name__} 是纯 classmethod 单例，禁止实例化")

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        """获取或创建锁（首次访问时延迟创建，避免跨事件循环问题）"""
        if cls._lock is None:
            cls._lock = asyncio.Lock()
        return cls._lock

    @classmethod
    async def _ensure_connected(cls, config: ServerConfig) -> aiosmtplib.SMTP:
        """确保 SMTP 连接可用，断开或未初始化时重新连接"""
        if cls._client is not None and cls._client.is_connected:
            return cls._client

        # 关闭旧连接（如果存在）
        if cls._client is not None:
            try:
                await cls._client.quit()
            except Exception:
                pass
            cls._client = None

        use_tls = config.smtp_encryption == SmtpEncryption.TLS
        start_tls = config.smtp_encryption == SmtpEncryption.STARTTLS

        client = aiosmtplib.SMTP(
            hostname=config.smtp_host,
            port=config.smtp_port,
            use_tls=use_tls,
            start_tls=start_tls,
        )

        try:
            await client.connect()
        except Exception as exc:
            l.error(f"SMTP 连接失败: {config.smtp_host}:{config.smtp_port} - {exc}")
            http_exceptions.raise_internal_error(E.MAIL_SMTP_ERROR, "邮件服务连接失败")

        # 认证
        if config.smtp_user and config.smtp_pass:
            try:
                await client.login(config.smtp_user, config.smtp_pass)
            except Exception as exc:
                l.error(f"SMTP 认证失败: {exc}")
                await client.quit()
                http_exceptions.raise_internal_error(E.MAIL_SMTP_ERROR, "邮件服务认证失败")

        cls._client = client
        l.info(f"SMTP 已连接: {config.smtp_host}:{config.smtp_port}")
        return client

    @classmethod
    def _reset_idle_timer(cls, keepalive: int) -> None:
        """重置空闲断开计时器"""
        if cls._idle_task is not None:
            cls._idle_task.cancel()
            cls._idle_task = None

        if keepalive <= 0:
            # keepalive=0 表示发送后立即断开
            cls._idle_task = asyncio.create_task(cls._idle_disconnect(0))
        else:
            cls._idle_task = asyncio.create_task(cls._idle_disconnect(keepalive))

    @classmethod
    async def _idle_disconnect(cls, delay: float) -> None:
        """空闲指定秒数后自动断开连接"""
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return

        async with cls._get_lock():
            if cls._client is not None and cls._client.is_connected:
                try:
                    await cls._client.quit()
                except Exception:
                    pass
                cls._client = None
                l.debug("SMTP 空闲超时，连接已断开")

    @classmethod
    async def send(cls, config: ServerConfig, to: str, subject: str, html: str) -> None:
        """
        发送一封 HTML 邮件

        :param config: 服务器配置（含 SMTP 参数）
        :param to: 收件人邮箱
        :param subject: 邮件主题
        :param html: HTML 正文
        :raises AppError: SMTP 连接或发送失败时抛出 500
        """
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{config.mail_from_name} <{config.mail_from_address}>"
        msg["To"] = to
        msg["Subject"] = subject
        if config.smtp_reply_to:
            msg["Reply-To"] = config.smtp_reply_to
        msg.attach(MIMEText(html, "html", "utf-8"))

        async with cls._get_lock():
            client = await cls._ensure_connected(config)
            try:
                await client.send_message(msg)
            except Exception as exc:
                l.error(f"SMTP 发送失败: to={to}, subject={subject}, error={exc}")
                # 连接可能已断开，清理状态
                cls._client = None
                http_exceptions.raise_internal_error(E.MAIL_SMTP_ERROR, "邮件发送失败")

            cls._reset_idle_timer(config.mail_keepalive)

        l.info(f"邮件已发送: to={to}, subject={subject}")

    @classmethod
    async def send_template(
        cls,
        config: ServerConfig,
        session: AsyncSession,
        to: str,
        template_type: MailTemplateType,
        subject: str,
        variables: dict[str, str | None],
    ) -> None:
        """
        从数据库加载邮件模板，渲染后发送

        :param config: 服务器配置
        :param session: 数据库会话
        :param to: 收件人邮箱
        :param template_type: 模板类型
        :param subject: 邮件主题
        :param variables: Jinja2 模板变量
        :raises AppError: 模板不存在或发送失败
        """
        template_record: MailTemplate | None = await MailTemplate.get(
            session,
            cond(MailTemplate.type == template_type),
        )
        if template_record is None:
            l.error(f"邮件模板不存在: {template_type.value}")
            http_exceptions.raise_internal_error(E.MAIL_TEMPLATE_NOT_FOUND, "邮件模板不存在")

        jinja_template = Template(template_record.content)
        html = jinja_template.render(**variables)

        await cls.send(config, to, subject, html)

    @classmethod
    async def shutdown(cls) -> None:
        """关闭 SMTP 连接（应用关闭时调用）"""
        if cls._idle_task is not None:
            cls._idle_task.cancel()
            cls._idle_task = None

        if cls._client is not None:
            try:
                await cls._client.quit()
            except Exception:
                pass
            cls._client = None
            l.info("SMTP 连接已关闭")

        cls._lock = None
