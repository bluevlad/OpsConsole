"""보안 헤더 미들웨어 — CSP / HSTS / X-Frame / X-Content-Type / Referrer-Policy.

운영 단계(P5):
- CSP: 기본 'self', img-src 도 https:만, connect-src 본 게이트웨이 + GitHub API
- HSTS: 1 year + includeSubDomains
- X-Frame-Options: DENY (클릭재킹 방어)
- X-Content-Type-Options: nosniff
- Referrer-Policy: strict-origin-when-cross-origin
- Permissions-Policy: 카메라/마이크/지오로케이션 등 비활성

dev 환경(APP_DEBUG=true)에서는 CSP 완화 — Vite HMR/inline script 호환.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.config import settings


def _csp_value() -> str:
    parts = [
        "default-src 'self'",
        "img-src 'self' data: https:",
        # Google Identity Services 스크립트
        "script-src 'self' https://accounts.google.com",
        "style-src 'self' 'unsafe-inline'",
        # 백엔드 API + GitHub API + Slack webhook 도메인 화이트리스트
        "connect-src 'self' https://api.github.com https://hooks.slack.com https://opsconsole.unmong.com",
        # iframe (Google Sign-In) 허용
        "frame-src https://accounts.google.com",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
    if settings.app_debug:
        # dev 환경에서 inline 스크립트/Vite HMR 허용
        parts = [p.replace("script-src 'self'", "script-src 'self' 'unsafe-inline' 'unsafe-eval'") for p in parts]
        # connect-src 에 localhost websocket 추가
        parts = [
            p.replace(
                "connect-src 'self'",
                "connect-src 'self' http://localhost:9100 ws://localhost:4100",
            )
            for p in parts
        ]
    return "; ".join(parts)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response: Response = await call_next(request)

        # CSP — API 응답에는 굳이 필요 없지만 통일성 위해 모두 적용
        response.headers["Content-Security-Policy"] = _csp_value()

        # HSTS — TLS 강제 (운영 도메인 한정 의미. dev 에서도 무해)
        if not settings.app_debug:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        # 클릭재킹 방어
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), interest-cohort=()"
        )

        return response


def configure_cors(app: FastAPI) -> None:
    """명시적 CORS — 와일드카드 금지, 메서드/헤더도 제한."""
    from fastapi.middleware.cors import CORSMiddleware

    origins = settings.cors_origins_list
    if "*" in origins:
        # 운영 안전장치 — 와일드카드 사용 시 부팅 실패
        raise ValueError(
            "BACKEND_CORS_ORIGINS 에 '*' 사용 금지. 명시적 origin 리스트 필요"
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Ops-Internal-Token"],
        expose_headers=["ETag", "Last-Modified"],
        max_age=600,
    )
