from .base import SQLModelBase

class ThemeResponse(SQLModelBase):
    """主题响应 DTO"""

    primary: str = "#3f51b5"
    """主色调"""

    secondary: str = "#f50057"
    """次要色"""

    accent: str = "#9c27b0"
    """强调色"""

    dark: str = "#1d1d1d"
    """深色"""

    dark_page: str = "#121212"
    """深色页面背景"""

    positive: str = "#21ba45"
    """正面/成功色"""

    negative: str = "#c10015"
    """负面/错误色"""

    info: str = "#31ccec"
    """信息色"""

    warning: str = "#f2c037"
    """警告色"""