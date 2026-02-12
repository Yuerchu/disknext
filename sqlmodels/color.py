from enum import StrEnum

from .base import SQLModelBase


class ChromaticColor(StrEnum):
    """有彩色枚举（17种 Tailwind 调色板颜色）"""

    RED = "red"
    ORANGE = "orange"
    AMBER = "amber"
    YELLOW = "yellow"
    LIME = "lime"
    GREEN = "green"
    EMERALD = "emerald"
    TEAL = "teal"
    CYAN = "cyan"
    SKY = "sky"
    BLUE = "blue"
    INDIGO = "indigo"
    VIOLET = "violet"
    PURPLE = "purple"
    FUCHSIA = "fuchsia"
    PINK = "pink"
    ROSE = "rose"


class NeutralColor(StrEnum):
    """无彩色枚举（5种灰色调）"""

    SLATE = "slate"
    GRAY = "gray"
    ZINC = "zinc"
    NEUTRAL = "neutral"
    STONE = "stone"


class ThemeColorsBase(SQLModelBase):
    """嵌套颜色 DTO，API 请求/响应层使用"""

    primary: ChromaticColor
    """主色调"""

    secondary: ChromaticColor
    """辅助色"""

    success: ChromaticColor
    """成功色"""

    info: ChromaticColor
    """信息色"""

    warning: ChromaticColor
    """警告色"""

    error: ChromaticColor
    """错误色"""

    neutral: NeutralColor
    """中性色"""


BUILTIN_DEFAULT_COLORS = ThemeColorsBase(
    primary=ChromaticColor.GREEN,
    secondary=ChromaticColor.BLUE,
    success=ChromaticColor.GREEN,
    info=ChromaticColor.BLUE,
    warning=ChromaticColor.YELLOW,
    error=ChromaticColor.RED,
    neutral=NeutralColor.ZINC,
)
