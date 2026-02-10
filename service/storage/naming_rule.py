"""
命名规则解析器

将包含占位符的规则模板转换为实际的文件名/目录路径。

支持的占位符：
- {date}: 当前日期 YYYY-MM-DD
- {timestamp}: Unix 时间戳
- {year}: 年份 YYYY
- {month}: 月份 MM
- {day}: 日期 DD
- {hour}: 小时 HH
- {minute}: 分钟 MM
- {randomkey16}: 16位随机字符串
- {originname}: 原始文件名（不含扩展名）
- {ext}: 文件扩展名（不含点）
- {uid}: 用户UUID
- {uuid}: 新生成的UUID
"""
import re
import secrets
import string
from datetime import datetime
from uuid import UUID, uuid4

from sqlmodels.base import SQLModelBase


class NamingContext(SQLModelBase):
    """
    命名上下文

    包含生成文件名/目录名所需的所有信息。
    """

    user_id: UUID
    """用户UUID"""

    original_filename: str
    """原始文件名（包含扩展名）"""

    timestamp: datetime | None = None
    """时间戳，默认为当前时间"""


class NamingRuleParser:
    """
    命名规则解析器

    将包含占位符的规则模板转换为实际的文件名/目录路径。

    使用示例::

        context = NamingContext(
            user_id=UUID("..."),
            original_filename="document.pdf",
        )
        dir_path = NamingRuleParser.parse("{date}/{randomkey16}", context)
        # -> "2025-12-23/a1b2c3d4e5f6g7h8"

        file_name = NamingRuleParser.parse("{randomkey16}_{originname}.{ext}", context)
        # -> "x9y8z7w6v5u4t3s2_document.pdf"
    """

    # 支持的占位符正则
    _PLACEHOLDER_PATTERN = re.compile(r'\{(\w+)\}')

    # 随机字符集
    _RANDOM_CHARS = string.ascii_lowercase + string.digits

    @classmethod
    def parse(cls, rule: str, context: NamingContext) -> str:
        """
        解析命名规则，替换所有占位符

        :param rule: 命名规则模板，如 "{date}/{randomkey16}"
        :param context: 命名上下文
        :return: 解析后的实际路径/文件名
        """
        timestamp = context.timestamp or datetime.now()

        # 解析原始文件名
        origin_name, ext = cls._split_filename(context.original_filename)

        # 占位符替换映射
        replacements: dict[str, str] = {
            'date': timestamp.strftime('%Y-%m-%d'),
            'timestamp': str(int(timestamp.timestamp())),
            'year': timestamp.strftime('%Y'),
            'month': timestamp.strftime('%m'),
            'day': timestamp.strftime('%d'),
            'hour': timestamp.strftime('%H'),
            'minute': timestamp.strftime('%M'),
            'randomkey16': cls._generate_random_key(16),
            'originname': origin_name,
            'ext': ext,
            'uid': str(context.user_id),
            'uuid': str(uuid4()),
        }

        def replace_placeholder(match: re.Match[str]) -> str:
            placeholder = match.group(1)
            return replacements.get(placeholder, match.group(0))

        return cls._PLACEHOLDER_PATTERN.sub(replace_placeholder, rule)

    @classmethod
    def _split_filename(cls, filename: str) -> tuple[str, str]:
        """
        分离文件名和扩展名

        :param filename: 完整文件名
        :return: (文件名不含扩展名, 扩展名不含点)
        """
        if '.' in filename:
            parts = filename.rsplit('.', 1)
            return parts[0], parts[1]
        return filename, ''

    @classmethod
    def _generate_random_key(cls, length: int) -> str:
        """
        生成随机字符串

        :param length: 字符串长度
        :return: 随机字符串
        """
        return ''.join(secrets.choice(cls._RANDOM_CHARS) for _ in range(length))

    @classmethod
    def validate_rule(cls, rule: str) -> bool:
        """
        验证命名规则是否有效

        :param rule: 命名规则模板
        :return: 是否有效
        """
        valid_placeholders = {
            'date', 'timestamp', 'year', 'month', 'day', 'hour', 'minute',
            'randomkey16', 'originname', 'ext', 'uid', 'uuid',
        }

        placeholders = cls._PLACEHOLDER_PATTERN.findall(rule)
        return all(p in valid_placeholders for p in placeholders)
