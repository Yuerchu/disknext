"""
SSRF 保护的 aiohttp Resolver

装饰器模式：委托 aiohttp ``AsyncResolver`` 做 DNS 解析，然后过滤所有私网/本地/
保留 IP。aiohttp 在每次连接（含 proxy、redirect、keep-alive 重连）前都会调用
resolver，所以把过滤做在 resolver 层可以彻底关闭 TOCTOU 窗口——检查点与
实际连接点是同一次 DNS 解析结果。
"""
import ipaddress
import socket
from typing import override

from aiohttp.abc import AbstractResolver, ResolveResult
from aiohttp.resolver import AsyncResolver
from loguru import logger as l


class UnsafeURLError(ValueError):
    """URL 包含不安全的主机名（内网 IP 或 localhost）"""


def _is_private_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """
    判断 IP 是否为内网地址。

    使用 ipaddress 标准库的内置方法：

    - is_private: 私有网络（10.x, 172.16-31.x, 192.168.x, fc00::/7）
    - is_loopback: 回环地址（127.x, ::1）
    - is_link_local: 链路本地地址（169.254.x, fe80::/10）
    - is_unspecified: 未指定地址（0.0.0.0, ::）
    - is_reserved: 保留地址
    - is_multicast: 多播地址
    """
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_unspecified
        or ip.is_reserved
        or ip.is_multicast
    )


class SSRFProtectedResolver(AbstractResolver):
    """
    DNS Resolver 装饰器：委托给 ``AsyncResolver``，然后剔除私网 IP

    - 若所有解析结果都是私网 IP → 抛 ``UnsafeURLError``（aiohttp 会转为连接失败）
    - 若部分私网、部分公网 → 只返回公网 IP 供连接使用
    - 若 DNS 解析失败 → 传递底层异常，aiohttp 处理

    :param nameservers: 传递给内部 ``AsyncResolver`` 的 DNS 列表，
        默认使用 aiohttp 的 AsyncResolver 默认值
    """

    def __init__(self, nameservers: list[str] | None = None) -> None:
        if nameservers:
            self._inner: AsyncResolver = AsyncResolver(nameservers=nameservers)
        else:
            self._inner = AsyncResolver()

    @override
    async def resolve(
        self,
        host: str,
        port: int = 0,
        family: socket.AddressFamily = socket.AF_INET,
    ) -> list[ResolveResult]:
        """
        解析主机名并过滤私网 IP

        :raises UnsafeURLError: 所有解析结果都是私网 IP
        """
        results: list[ResolveResult] = await self._inner.resolve(host, port, family)

        safe: list[ResolveResult] = []
        rejected: list[str] = []

        for entry in results:
            ip_str: str = entry['host']
            try:
                ip_obj = ipaddress.ip_address(ip_str)
            except ValueError:
                # 解析结果不是合法 IP 字符串，罕见但保守放行给 aiohttp 处理
                safe.append(entry)
                continue

            if _is_private_ip(ip_obj):
                rejected.append(ip_str)
                continue
            safe.append(entry)

        if not safe:
            # 全部被拒 → 连接彻底失败
            raise UnsafeURLError(
                f"SSRF 拦截: 主机 {host} 的所有解析结果均为私网 IP: {rejected}"
            )

        if rejected:
            l.warning(
                f"[SSRFProtectedResolver] 主机 {host} 部分 IP 被拒: "
                f"rejected={rejected}, accepted={[e['host'] for e in safe]}"
            )

        return safe

    @override
    async def close(self) -> None:
        """关闭底层 resolver 资源"""
        await self._inner.close()
