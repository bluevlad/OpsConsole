"""SSRF 방어 — 매니페스트의 health.url 이 임의 URL 호출을 못하도록 검증.

차단 대상:
- 비-HTTP(S) 스킴 (file:// gopher:// ftp:// 등)
- 사설 IP / 루프백 / 링크-로컬 / 메타데이터 IP (AWS/GCP 169.254.169.254)
- 잘못된 host
- HTTP_PROBE_ALLOW_PRIVATE=true 환경에선 우회 (개발용)

DNS 재바인딩(rebinding) 방어:
- httpx 호출 직전 별도 단계로 hostname → IP 해석 후 동일 IP 로 직접 호출하는 패턴은
  본 단계에서 미적용 (overhead 큼). 대신 hostname-allowlist 옵션으로 보강 가능.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from app.core.config import settings

ALLOWED_SCHEMES = ("http", "https")

# Cloud metadata + 사설 + 루프백 등 차단
PRIVATE_NETS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local + AWS metadata
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("224.0.0.0/4"),    # multicast
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),       # ULA IPv6
    ipaddress.ip_network("fe80::/10"),      # link-local IPv6
]


class UnsafeURLError(ValueError):
    pass


def _is_private(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return any(ip in net for net in PRIVATE_NETS)


def assert_safe_probe_url(url: str) -> None:
    """매니페스트 health.url 이 외부 공개 호스트인지 검증."""
    if settings.app_debug and getattr(settings, "health_probe_allow_private", False):
        return  # dev 우회

    if not url:
        raise UnsafeURLError("empty url")
    parsed = urlparse(url.strip())
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise UnsafeURLError(f"scheme '{parsed.scheme}' not allowed (http/https only)")
    if not parsed.hostname:
        raise UnsafeURLError("missing hostname")

    host = parsed.hostname
    # IP literal 직접 차단
    if _is_private(host):
        raise UnsafeURLError(f"private/loopback IP not allowed: {host}")

    # DNS 해석 후 차단 — 외부 도메인이지만 사설 IP로 resolve 되는 경우
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        # DNS 해석 실패 — 후속 httpx 호출에서도 실패. 차단 효과는 동일
        return
    for info in infos:
        addr = info[4][0]
        if _is_private(addr):
            raise UnsafeURLError(
                f"hostname '{host}' resolves to private IP {addr} — DNS rebinding 의심"
            )
