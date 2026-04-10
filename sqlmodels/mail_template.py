from enum import StrEnum

from sqlmodel import UniqueConstraint

from sqlmodel_ext import SQLModelBase, TableBaseMixin


class MailTemplateType(StrEnum):
    """邮件模板类型"""
    ACTIVATION = "activation"
    """邮箱激活验证码"""
    RESET_PASSWORD = "reset_password"
    """重置密码验证码"""


class MailTemplateBase(SQLModelBase):
    """邮件模板基类"""

    type: MailTemplateType
    """模板类型"""

    content: str
    """HTML 模板内容（Jinja2 变量）"""


class MailTemplate(MailTemplateBase, TableBaseMixin):
    """邮件模板（独立存储长文本 HTML）"""

    __table_args__ = (UniqueConstraint("type", name="uq_mail_template_type"),)
