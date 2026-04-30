"""감사 로그·로그·디버그 출력에서 민감 정보 마스킹.

규칙:
- 이메일: local-part 첫 3자만 노출 ('rainend00@gmail.com' → 'rai***@gmail.com')
- token/secret/key/password: 값 전체 ***
- bearer token: 'Bearer ***'

dict 마스킹은 재귀 적용. 화이트리스트 키는 그대로 통과.
"""
from __future__ import annotations

from typing import Any

# 키 이름이 다음 단어를 포함하면 마스킹
SENSITIVE_KEY_PARTS = (
    "password",
    "secret",
    "token",
    "credential",
    "private_key",
    "client_secret",
    "session",
    "_pat",      # github_pat, gitlab_pat 등 ('pat' 단독은 path/pattern 충돌)
    "api_key",
    "apikey",
    "auth_key",
)
# 마스킹 면제 키 — 길이 표시 등 메타 정보
EXEMPT_KEYS = ("len", "length", "version", "id", "ref")


def mask_email(s: str | None) -> str | None:
    if not s or "@" not in s:
        return s
    local, domain = s.split("@", 1)
    if len(local) <= 3:
        return "***@" + domain
    return local[:3] + "***@" + domain


def mask_value(s: Any) -> Any:
    if s is None:
        return None
    if isinstance(s, str):
        if len(s) > 12:
            return s[:4] + "***" + s[-2:]
        return "***"
    return "***"


def _is_sensitive(key: str) -> bool:
    if key in EXEMPT_KEYS:
        return False
    lower = key.lower()
    return any(part in lower for part in SENSITIVE_KEY_PARTS)


def mask_payload(obj: Any) -> Any:
    """audit log payload 등 dict/list/scalar 재귀 마스킹."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if _is_sensitive(str(k)):
                out[k] = mask_value(v)
            elif isinstance(k, str) and "email" in k.lower() and isinstance(v, str):
                out[k] = mask_email(v)
            else:
                out[k] = mask_payload(v)
        return out
    if isinstance(obj, list):
        return [mask_payload(x) for x in obj]
    return obj
