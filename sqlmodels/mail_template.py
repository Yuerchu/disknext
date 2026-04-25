from enum import StrEnum

from sqlmodel import Field

from sqlmodel_ext import SQLModelBase, UUIDTableBaseMixin, Text1M


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

    content: Text1M
    """HTML 模板内容（Jinja2 变量）"""


class MailTemplate(MailTemplateBase, UUIDTableBaseMixin):
    """邮件模板（独立存储长文本 HTML）"""

    type: MailTemplateType = Field(unique=True)
    """模板类型"""
