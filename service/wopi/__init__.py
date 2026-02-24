"""
WOPI Discovery 服务模块

解析 WOPI 服务端（Collabora / OnlyOffice 等）的 Discovery XML，
提取支持的文件扩展名及对应的编辑器 URL 模板。

参考：Cloudreve pkg/wopi/discovery.go 和 pkg/wopi/wopi.go
"""
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from loguru import logger as l

# WOPI URL 模板中已知的查询参数占位符及其替换值
# 值为 None 表示删除该参数，非 None 表示替换为该值
# 参考 Cloudreve pkg/wopi/wopi.go queryPlaceholders
_WOPI_QUERY_PLACEHOLDERS: dict[str, str | None] = {
    'BUSINESS_USER': None,
    'DC_LLCC': 'lng',
    'DISABLE_ASYNC': None,
    'DISABLE_CHAT': None,
    'EMBEDDED': 'true',
    'FULLSCREEN': 'true',
    'HOST_SESSION_ID': None,
    'SESSION_CONTEXT': None,
    'RECORDING': None,
    'THEME_ID': 'darkmode',
    'UI_LLCC': 'lng',
    'VALIDATOR_TEST_CATEGORY': None,
}

_WOPI_SRC_PLACEHOLDER = 'WOPI_SOURCE'


def process_wopi_action_url(raw_urlsrc: str) -> str:
    """
    将 WOPI Discovery 中的原始 urlsrc 转换为 DiskNext 可用的 URL 模板。

    处理流程（参考 Cloudreve generateActionUrl）：
    1. 去除 ``<>`` 占位符标记
    2. 解析查询参数，替换/删除已知占位符
    3. ``WOPI_SOURCE`` → ``{wopi_src}``

    注意：access_token 和 access_token_ttl 不放在 URL 中，
    根据 WOPI 规范它们通过 POST 表单字段传递给编辑器。

    :param raw_urlsrc: WOPI Discovery XML 中的 urlsrc 原始值
    :return: 处理后的 URL 模板字符串，包含 {wopi_src} 占位符
    """
    # 去除 <> 标记
    cleaned = raw_urlsrc.replace('<', '').replace('>', '')
    parsed = urlparse(cleaned)
    raw_params = parse_qs(parsed.query, keep_blank_values=True)

    new_params: list[tuple[str, str]] = []
    is_src_replaced = False

    for key, values in raw_params.items():
        value = values[0] if values else ''

        # WOPI_SOURCE 占位符 → {wopi_src}
        if value == _WOPI_SRC_PLACEHOLDER:
            new_params.append((key, '{wopi_src}'))
            is_src_replaced = True
            continue

        # 已知占位符
        if value in _WOPI_QUERY_PLACEHOLDERS:
            replacement = _WOPI_QUERY_PLACEHOLDERS[value]
            if replacement is not None:
                new_params.append((key, replacement))
            # replacement 为 None 时删除该参数
            continue

        # 其他参数保留原值
        new_params.append((key, value))

    # 如果没有找到 WOPI_SOURCE 占位符，手动添加 WOPISrc
    if not is_src_replaced:
        new_params.append(('WOPISrc', '{wopi_src}'))

    # LibreOffice/Collabora 需要 lang 参数（避免重复添加）
    existing_keys = {k for k, _ in new_params}
    if 'lang' not in existing_keys:
        new_params.append(('lang', 'lng'))

    # 注意：access_token 和 access_token_ttl 不放在 URL 中
    # 根据 WOPI 规范，它们通过 POST 表单字段传递给编辑器

    # 重建 URL
    new_query = urlencode(new_params, safe='{}')
    result = urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        new_query,
        '',
    ))

    return result


def parse_wopi_discovery_xml(xml_content: str) -> tuple[dict[str, str], list[str]]:
    """
    解析 WOPI Discovery XML，提取扩展名到 URL 模板的映射。

    XML 结构::

        <wopi-discovery>
          <net-zone name="external-https">
            <app name="Writer" favIconUrl="...">
              <action name="edit" ext="docx" urlsrc="https://..."/>
              <action name="view" ext="docx" urlsrc="https://..."/>
            </app>
          </net-zone>
        </wopi-discovery>

    动作优先级：edit > embedview > view（参考 Cloudreve discovery.go）

    :param xml_content: WOPI Discovery 端点返回的 XML 字符串
    :return: (action_urls, app_names) 元组
             action_urls: {extension: processed_url_template}
             app_names: 发现的应用名称列表
    :raises ValueError: XML 解析失败或格式无效
    """
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        raise ValueError(f"WOPI Discovery XML 解析失败: {e}")

    # 查找 net-zone（可能有多个，取第一个非空的）
    net_zones = root.findall('net-zone')
    if not net_zones:
        raise ValueError("WOPI Discovery XML 缺少 net-zone 节点")

    # ext_actions: {extension: {action_name: urlsrc}}
    ext_actions: dict[str, dict[str, str]] = {}
    app_names: list[str] = []

    for net_zone in net_zones:
        for app_elem in net_zone.findall('app'):
            app_name = app_elem.get('name', '')
            if app_name:
                app_names.append(app_name)

            for action_elem in app_elem.findall('action'):
                action_name = action_elem.get('name', '')
                ext = action_elem.get('ext', '')
                urlsrc = action_elem.get('urlsrc', '')

                if not ext or not urlsrc:
                    continue

                # 只关注 edit / embedview / view 三种动作
                if action_name not in ('edit', 'embedview', 'view'):
                    continue

                if ext not in ext_actions:
                    ext_actions[ext] = {}
                ext_actions[ext][action_name] = urlsrc

    # 为每个扩展名选择最佳 URL: edit > embedview > view
    action_urls: dict[str, str] = {}
    for ext, actions_map in ext_actions.items():
        selected_urlsrc: str | None = None
        for preferred in ('edit', 'embedview', 'view'):
            if preferred in actions_map:
                selected_urlsrc = actions_map[preferred]
                break

        if selected_urlsrc:
            action_urls[ext] = process_wopi_action_url(selected_urlsrc)

    # 去重 app_names
    seen: set[str] = set()
    unique_names: list[str] = []
    for name in app_names:
        if name not in seen:
            seen.add(name)
            unique_names.append(name)

    l.info(f"WOPI Discovery 解析完成: {len(action_urls)} 个扩展名, 应用: {unique_names}")

    return action_urls, unique_names
