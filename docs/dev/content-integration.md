# 본 서비스 측 콘텐츠 통합 가이드 (P3)

> AllergyInsight 등 본 서비스가 OpsConsole 의 published 콘텐츠 블록을 받아
> 사용자 화면에 반영하기 위한 통합 절차.

---

## 0. 개요

```
┌──────────────────┐  GET /api/internal/content/published   ┌────────────┐
│ AllergyInsight   ├──────────────────────────────────────►│ OpsConsole │
│ scheduler (5분)  │  X-Ops-Internal-Token: <shared-secret>│ FastAPI    │
└────────┬─────────┘  If-None-Match: <last_etag>           └────────────┘
         │ payload (200) 또는 304
         ▼
┌──────────────────┐
│ in-memory cache  │  → 페이지 렌더 시 사용
│ or Redis         │
└──────────────────┘
```

- OpsConsole 은 콘텐츠의 SSoT. 본 서비스는 **읽기만** 한다.
- ETag 가 일치하면 304 → 본 서비스 캐시 그대로 사용. 네트워크·CPU 절감.
- 사용자 JWT 사용 안 함. 별도 공유 비밀(`OPS_INTERNAL_TOKEN`).

---

## 1. 양 쪽 .env 설정

OpsConsole 측 (`.env`):
```bash
OPS_INTERNAL_TOKEN=<32+ chars random>
```

본 서비스(예: AllergyInsight) 측 (`.env`):
```bash
OPS_CONSOLE_BASE_URL=https://opsconsole.unmong.com
OPS_INTERNAL_TOKEN=<위와 동일한 값>
```

비밀번호 생성:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## 2. 본 서비스 구현 (참고 코드)

### 2.1 polling client (FastAPI 예시)

```python
# allergyinsight/backend/app/ops_content/polling_client.py
from __future__ import annotations
import asyncio, logging, os
from datetime import datetime
from typing import Any
import httpx

OPS_BASE = os.environ["OPS_CONSOLE_BASE_URL"].rstrip("/")
OPS_TOKEN = os.environ["OPS_INTERNAL_TOKEN"]
SERVICE_CODE = "allergyinsight"

class OpsContentCache:
    """in-memory 캐시 (단일 프로세스). 다중 워커는 Redis 권장."""
    def __init__(self) -> None:
        self.payload: dict[str, Any] = {}
        self.etag: str | None = None
        self.last_fetched_at: datetime | None = None

    def get_block(self, section_code: str, key: str, locale: str = "ko") -> str | None:
        sec = self.payload.get(section_code) or {}
        loc = (sec.get(key) or {}).get(locale) or {}
        return loc.get("body")

cache = OpsContentCache()
log = logging.getLogger("opsconsole.polling")

async def refresh_once(timeout_s: float = 8.0) -> bool:
    headers = {"X-Ops-Internal-Token": OPS_TOKEN}
    if cache.etag:
        headers["If-None-Match"] = cache.etag
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        try:
            res = await client.get(
                f"{OPS_BASE}/api/internal/content/published",
                params={"service": SERVICE_CODE},
                headers=headers,
            )
        except httpx.RequestError as e:
            log.warning("[ops-polling] request error: %s", e)
            return False
    if res.status_code == 304:
        return False  # cache 그대로 사용
    if res.status_code != 200:
        log.warning("[ops-polling] %s: %s", res.status_code, res.text[:200])
        return False
    cache.payload = res.json().get(SERVICE_CODE, {})
    cache.etag = res.headers.get("ETag")
    cache.last_fetched_at = datetime.utcnow()
    log.info("[ops-polling] refreshed (etag=%s)", cache.etag)
    return True
```

### 2.2 5분 주기 잡

기존 APScheduler / Celery / cron 어디든. 예시:

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

scheduler = AsyncIOScheduler()
scheduler.add_job(refresh_once, IntervalTrigger(minutes=5), id="ops_content_polling")
scheduler.start()

# 부팅 직후 1회 즉시
await refresh_once()
```

### 2.3 페이지 렌더 시 사용

```python
# AI 상담 페이지 핸들러 안에서
banner_md = cache.get_block("ai-consult", "ai_consult.intro_banner") or ""
return TemplateResponse("ai_consult.html", {"banner_md": banner_md, ...})
```

또는 API 응답에 포함:

```python
@router.get("/api/ai/consult/page-meta")
async def page_meta():
    return {
        "banner_md": cache.get_block("ai-consult", "ai_consult.intro_banner") or "",
        "fetched_at": cache.last_fetched_at,
    }
```

프런트는 `banner_md` 를 `marked` + `DOMPurify` 로 렌더 (OpsConsole 과 같은 패턴).

---

## 3. 응답 스키마

`GET /api/internal/content/published?service=allergyinsight` 200:

```json
{
  "allergyinsight": {
    "ai-consult": {
      "ai_consult.intro_banner": {
        "ko": {
          "body": "# 안녕하세요\n오늘의 안내...",
          "format": "markdown",
          "version": 3,
          "published_at": "2026-04-30T05:30:00+00:00"
        }
      }
    },
    "newsletter": {
      "newsletter.welcome_template": {
        "ko": { ... },
        "en": { ... }
      }
    }
  }
}
```

응답 헤더:
- `ETag`: `"<32-char hex>"` — 다음 요청에 `If-None-Match` 로 보냄
- `Last-Modified`: 가장 최근 게시 시각 (RFC 1123)
- `Cache-Control`: `private, max-age=0`

`If-None-Match` 일치 시:
- HTTP 304, 본문 없음. 본 서비스는 기존 캐시 사용.

---

## 4. 화이트리스트 등록

본 서비스가 새로운 콘텐츠 블록을 OpsConsole 에서 편집받으려면 **매니페스트** 에 등록 필요.

`AllergyInsight/ops/manifest.yml` 예:

```yaml
sections:
  - code: ai-consult
    name: AI 상담
    ...
    content_blocks:
      - key: ai_consult.intro_banner
        format: markdown
        max_length: 2000
        locales: [ko]
        description: "AI 상담 페이지 상단 안내 배너"
```

매니페스트 갱신 후 OpsConsole 에서 `POST /api/catalog/sync` 호출하면
`/services/allergyinsight/sections/ai-consult/content` 페이지에 새 블록이 노출된다.

키 네이밍 규약: `{section_code}.{block_name}` (소문자, snake_case)

---

## 5. 트러블슈팅

| 증상 | 원인 / 조치 |
|------|------------|
| 401 invalid X-Ops-Internal-Token | 양 쪽 `.env` 의 `OPS_INTERNAL_TOKEN` 불일치. 두 컨테이너 모두 재시작 후 재확인 |
| 503 OPS_INTERNAL_TOKEN 미설정 | OpsConsole 측 `.env` 비어있음 |
| 빈 payload 받음 (`{}`) | 1) 매니페스트의 `content_blocks` 등록 누락 2) 아직 published 블록 없음 |
| 304 가 너무 자주 — 갱신 안됨 | 정상. ETag 가 같으면 변경 없음. 본 서비스는 cache 그대로 사용 |
| 본 서비스 페이지에 반영 안 됨 | polling 잡 동작 확인. `cache.last_fetched_at` 가 최근인지 |

---

## 6. 보안 노트

- `OPS_INTERNAL_TOKEN` 은 양 쪽 `.env` 에만 — 절대 커밋 금지 (`.gitignore` 등재 필수)
- 본 서비스가 외부에 노출하는 endpoint 라면 token 도 함께 노출되지 않도록 주의
- 정기 회전 (분기 1회 권장)
- token 변경 시: OpsConsole `.env` → 본 서비스 `.env` → 양 쪽 컨테이너 재시작 (그 사이는 401 일시 발생, recover)
