# OpsConsole — 시스템 전체 가이드

> 멀티 서비스 운영 콘솔 (Internal Developer Portal). 1호 고객 AllergyInsight, 향후 unmong-main / EduFit 등 unmong.com 산하 전체.
>
> 본 문서는 **이미 구현된 P0~P5 의 단일 진입점**. 새로 합류하는 개발자/운영자가 30분 내 시스템 전체 그림을 잡기 위함.

---

## 0. 30초 요약

OpsConsole 은 본 서비스 코드를 거의 건드리지 않고(매니페스트 1개 파일만 추가) 다음 5가지를 제공한다:

1. **카탈로그** — 매니페스트(`ops/manifest.yml`)의 섹션·자산을 자동 동기화·표시
2. **헬스 모니터링** — 5분 주기 점검 + 실패 시 Slack 알림 + 24h 가용률
3. **변경요청** — 운영자 폼 → GitHub Issue 자동 발급 + PR 머지 시 상태 동기화
4. **콘텐츠 편집** — 매니페스트 화이트리스트 텍스트 블록을 OpsConsole 에서 편집·게시 → 본 서비스가 polling
5. **트레이 앱** — 데스크톱(Windows/macOS/Linux)에서 위 기능 미러링 + OS 푸시 알림

운영자 권한 (`ops_admin`/`reviewer`/`member`/`viewer`)은 본 서비스의 권한 모델과 **완전 분리**.

---

## 1. 아키텍처

```
┌──────────────┐       ┌──────────────┐
│ 사용자/운영자 │       │ 트레이 앱     │
│ (브라우저)    │       │ (Tauri)       │
└──────┬───────┘       └──────┬───────┘
       │ HTTPS                 │ HTTPS
       ▼                       ▼
       ┌─────────────────────────────┐
       │  unmong-gateway (nginx)     │  *.unmong.com Let's Encrypt
       └────────┬────────────────────┘
                │
       ┌────────▼────────────┐    ┌─────────────────────────┐
       │ opsconsole-frontend │    │ opsconsole-backend      │
       │ React 18 + Vite     │    │ FastAPI + SQLAlchemy    │
       │ :4100               │    │ :9100                   │
       └─────────────────────┘    │ + APScheduler 5분 잡    │
                                  └────────┬────────────────┘
                                           │ database-network
            ┌──────────────────────────────┼──────────────────────────────┐
            │                              │                              │
   ┌────────▼────────┐         ┌──────────▼─────────┐         ┌──────────▼──────────┐
   │ postgresql       │         │ GitHub API         │         │ 본 서비스           │
   │ opsconsole(_dev) │         │ Issues + Webhook   │         │ AllergyInsight 등   │
   │ 11 ops_* tables  │         │ + raw manifest     │         │ /internal/content/  │
   └──────────────────┘         └────────────────────┘         │  published polling  │
                                                                └─────────────────────┘
                                  ┌──────────────────────────┐
                                  │ Slack Incoming Webhook   │
                                  │ #allergy-ops             │
                                  └──────────────────────────┘
```

### 주요 컨테이너

| 컨테이너 | 이미지 | 포트 | 역할 |
|----------|--------|------|------|
| `opsconsole-backend` | python:3.11-slim + FastAPI | 9100 | API + APScheduler 헬스 잡 |
| `opsconsole-frontend` | node:20-alpine + Vite (dev) / nginx:1.27 (prod) | 4100 | React 운영자 UI |
| `postgresql` (공유) | pgvector/pgvector:pg15 | 5432 | DB (`opsconsole`/`opsconsole_dev`) |
| `unmong-gateway` (공유) | nginx:1.27 | 80/443 | `opsconsole.unmong.com` 라우팅 |

---

## 2. 데이터 모델 (11 테이블 + alembic 4 revisions)

| Phase | 테이블 | 용도 |
|-------|--------|------|
| P0 | `ops_services` | 등록 서비스 카탈로그 |
| P0 | `ops_sections` (UNIQUE service+code) | 섹션 카탈로그 |
| P0 | `ops_section_assets` | 섹션 ↔ 자산 (frontend/router/service/model/table/endpoint) |
| P0 | `ops_users` (UNIQUE email) | 운영자 계정 (Google OAuth) |
| P0 | `ops_audit_log` (JSONB payload, ix_at) | 모든 쓰기 작업 감사 |
| P0 | `ops_manifest_snapshots` (JSONB, ref) | 매니페스트 시계열 |
| P1 | `ops_section_permissions` (UNIQUE section+user) | can_edit_content / can_open_pr / can_publish |
| P1 | `ops_health_snapshots` (ix_section_time) | 5분 헬스 시계열 |
| P1 | `ops_alert_state` (PK section_id) | 디듀프 (consecutive_failures, last_alerted_at, resolved_notified) |
| P2 | `ops_change_requests` (FK section SET NULL) | 변경요청 폼 + GitHub Issue/PR 미러 |
| P2 | `ops_change_request_events` (ix_github_event_id) | webhook 이력 + idempotency |
| P3 | `ops_content_blocks` (UNIQUE section+key+locale) | draft + published_body + status 워크플로 |
| P3 | `ops_content_block_versions` (UNIQUE block+version) | 게시 스냅샷 |
| P4 | `ops_device_codes` (PK device_code, UNIQUE user_code) | Tauri 트레이 디바이스 코드 OAuth |

마이그레이션 head: `1bd3e01cab2b` (P4 device_codes).

---

## 3. API 카탈로그

### 인증

| Method | Path | 권한 | 비고 |
|--------|------|------|------|
| POST | `/api/auth/google/verify` | 누구나 | Google ID token → JWT |
| GET | `/api/auth/me` | bearer | 현재 사용자 |
| POST | `/api/auth/device/init` | 누구나 | 트레이용 device_code/user_code |
| POST | `/api/auth/device/poll` | 누구나(device_code) | pending / approved+token / 410 |
| GET | `/api/auth/device/lookup` | bearer | 웹 승인 화면 |
| POST | `/api/auth/device/approve` | bearer | 디바이스 승인 |

### 카탈로그

| Method | Path | 권한 | 비고 |
|--------|------|------|------|
| GET | `/api/catalog/services` | bearer | section_count 포함 |
| GET | `/api/catalog/services/{code}` | bearer | 단일 |
| GET | `/api/catalog/services/{code}/sections` | bearer | health 요약 포함 |
| GET | `/api/catalog/services/{code}/sections/{section}` | bearer | + assets + health |
| POST | `/api/catalog/sync` | bearer | mode: github/local/inline |

### My / 권한

| Method | Path | 권한 | 비고 |
|--------|------|------|------|
| GET | `/api/my/sections` | bearer | owner/backup/permission 매칭 + 헬스 |
| GET | `/api/assignments?section_id=...` | ops_admin | |
| POST | `/api/assignments` | ops_admin | placeholder user 자동 생성 |
| DELETE | `/api/assignments/{id}` | ops_admin | |

### 헬스

| Method | Path | 권한 |
|--------|------|------|
| GET | `/api/health/snapshots/{svc}/{sec}?limit=N` | bearer |
| GET | `/api/health/summary/{svc}/{sec}` | bearer |
| POST | `/api/health/probe/run` | ops_admin |

### 변경요청

| Method | Path | 권한 | 비고 |
|--------|------|------|------|
| POST | `/api/change-requests` | bearer | + GitHub Issue 자동 발급 |
| GET | `/api/change-requests?mine&status&section_id` | bearer | |
| GET | `/api/change-requests/{id}` | bearer | |
| PATCH | `/api/change-requests/{id}` | bearer (title/desc) / ops_admin (status) | |
| POST | `/api/github/webhook` | HMAC | issues/pull_request/ping |

### 콘텐츠

| Method | Path | 권한 |
|--------|------|------|
| GET | `/api/content/sections/{svc}/{sec}/blocks` | bearer |
| GET | `/api/content/blocks/{id}` | bearer |
| PUT | `/api/content/sections/{svc}/{sec}/blocks/{key}/draft` | can_edit_content |
| POST | `/api/content/blocks/{id}/request-review` | can_edit_content |
| POST | `/api/content/blocks/{id}/approve` | can_publish |
| POST | `/api/content/blocks/{id}/reject` | can_publish |
| POST | `/api/content/blocks/{id}/publish` | can_publish |
| GET | `/api/content/blocks/{id}/versions` | bearer |

### 본 서비스용 (별도 토큰)

| Method | Path | 인증 |
|--------|------|------|
| GET | `/api/internal/content/published?service=...` | X-Ops-Internal-Token + ETag/304 |

### 감사

| Method | Path | 권한 | 비고 |
|--------|------|------|------|
| GET | `/api/audit-log?action&target_type&actor_id&limit` | ops_admin | 마스킹 자동 |

---

## 4. 권한 매트릭스 (P5)

| 역할 | 카탈로그 | sync | 담당자 지정 | 콘텐츠 편집 | 콘텐츠 게시 | 변경요청 | 감사 조회 |
|------|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| ops_viewer | ✅ | — | — | — | — | — | — |
| ops_member | ✅ | — | — | 자기 섹션* | — | ✅ | — |
| ops_reviewer | ✅ | — | — | ✅* | ✅* | ✅ | — |
| ops_admin | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

\* `ops_section_permissions.can_edit_content` / `can_publish` 별도 부여 필요. ops_admin은 모든 섹션 자동 통과.

---

## 5. 프런트 라우트

| Path | 권한 | 페이지 |
|------|------|--------|
| `/` | 누구나 | HomePage (랜딩 + 로드맵) |
| `/login` | 누구나 | LoginPage (Google Sign-In) |
| `/device` | bearer | DeviceApprovalPage (`?code=XXXX-XXXX` 자동 lookup) |
| `/services` | bearer | ServicesListPage (카탈로그 표) |
| `/services/{code}/sections` | bearer | SectionsListPage (헬스 dot + 자산수) |
| `/services/{code}/sections/{section}` | bearer | SectionDetailPage (메타 + 헬스 + 자산 + 변경요청) |
| `/services/{code}/sections/{section}/content` | bearer | SectionContentPage (마크다운 에디터 + 미리보기 + 워크플로) |
| `/services/{code}/sections/{section}/permissions` | ops_admin | PermissionsPage (부여/해제) |
| `/my/sections` | bearer | MySectionsPage |
| `/my/change-requests` | bearer | MyChangeRequestsPage |
| `/change-requests/new?service=&section=` | bearer | ChangeRequestNewPage |
| `/change-requests/{id}` | bearer | ChangeRequestDetailPage (admin status 전이) |

---

## 6. 백그라운드 잡 / 외부 통신

| 잡 | 주기 | 동작 |
|----|------|------|
| `health_probe` (APScheduler) | 5분 | 매니페스트 health.url/api 호출 → 시계열 INSERT → 알림 라우팅 |
| `alert_router` (헬스 잡 내부) | event-driven | 3회 연속 실패 → Slack + 1h cooldown / 회복 시 1회 |

| 외부 통신 | 인증 | 용도 |
|----------|------|------|
| GitHub Contents API | Bearer PAT | 매니페스트 fetch (P0 §2 fetcher) |
| GitHub Issues API | Bearer PAT | 변경요청 → Issue 자동 발급 (P2) |
| GitHub Webhook | HMAC-SHA256 | PR 머지/이슈 종료 → 상태 동기화 (P2) |
| Slack Incoming Webhook | URL 자체 | 헬스 실패 알림 (P1) |
| Google ID Token verify | client_id audience | 사용자 로그인 (P0) |

---

## 7. 보안 (P5)

- **JWT** HS256 / 12h expire / `JWT_SECRET_KEY` 분기 회전
- **CORS** `BACKEND_CORS_ORIGINS` 명시 (와일드카드 거부)
- **CSP** default-src 'self', frame-ancestors 'none', connect-src 화이트리스트
- **HSTS / X-Frame DENY / nosniff / Referrer-Policy / Permissions-Policy**
- **마스킹** 이메일·토큰·secret 자동 (audit log + 디버그 출력)
- **SSRF** 헬스 probe URL 검증 (사설/loopback/링크-로컬 + DNS 재바인딩 차단)
- **HMAC-SHA256** GitHub webhook + idempotency
- **OS Keychain** 트레이 토큰 저장 (`opsconsole-tray` service)

CI 보안 4종 (`.github/workflows/security.yml`):
- gitleaks (커밋 history 시크릿)
- pip-audit (Python deps CVE)
- npm audit (frontend + tray)
- bandit (Python static security)

---

## 8. 테스트

`backend/tests/` 11 파일 / **114건 그린**:

| 영역 | 케이스 |
|------|--------|
| health (P0) | 1 |
| manifest schema/parser/fetcher/sync (P0 §2) | 27 |
| catalog API (P0 §2) | 5 |
| auth Google + JWT (P0 잔여) | 6 |
| P1 my-sections / assignments / health snapshots | 7 |
| notify dedup + cooldown + recovery (P1) | 5 |
| health_probe (P1) | 3 |
| github issue_builder (P2) | 5 |
| github webhook (HMAC + idempotency) | 11 |
| change_requests API + webhook endpoint | 9 |
| content workflow + internal endpoint (P3) | 9 |
| device code OAuth (P4) | 8 |
| P5 security (role/mask/SSRF/audit/headers) | 18 |

실행:
```bash
cd backend && .venv/bin/python -m pytest    # 0.7s 전체
```

---

## 9. 운영 활성화 체크리스트

OpsConsole `.env`:
- [ ] `JWT_SECRET_KEY` — 32+ chars random (운영 시 분기 회전)
- [ ] `DATABASE_URL` — `database-setup.md` 의 SQL 실행 후 비밀번호 반영
- [ ] `GOOGLE_OAUTH_CLIENT_ID` — AllergyInsight 와 동일 (Google Cloud 발급)
- [ ] `GITHUB_PAT` — issues:write + contents:read (fine-grained 권장)
- [ ] `GITHUB_WEBHOOK_SECRET` — 32+ chars, GitHub 측 webhook 등록 시 동일
- [ ] `SLACK_WEBHOOK_URL` — `#allergy-ops` Incoming Webhook
- [ ] `OPS_INTERNAL_TOKEN` — 본 서비스 polling client 와 공유

GitHub 설정:
- [ ] 각 서비스 레포에 라벨 13종 사전 생성 (`docs/dev/github-bridge.md §3`)
- [ ] 각 서비스 레포에 webhook 등록 (`opsconsole.unmong.com/api/github/webhook`)

본 서비스 측:
- [ ] 매니페스트 `ops/manifest.yml` 작성·커밋
- [ ] (P3 활용 시) polling client 구현 (`docs/dev/content-integration.md`)
- [ ] AllergyInsight 등 매니페스트의 `content_blocks` 화이트리스트 등록

트레이 앱 (선택):
- [ ] Rust toolchain 설치 + `cd tray && npm run tauri:dev`
- [ ] Apple Developer ($99/yr) + Windows EV 코드 서명 인증서
- [ ] GitHub Secrets 8개 등록 (`docs/dev/tray-build.md §5`)
- [ ] `tray-v0.0.1` 태그 push → CI 빌드·서명·릴리스

운영 잡:
- [ ] DB 백업 cron (`docs/dev/backup-restore.md §2`)
- [ ] 외부 모니터링 (UptimeRobot 등) 등록 — `https://opsconsole.unmong.com/api/health`
- [ ] 분기 1회 OWASP 점검 (`docs/dev/owasp-checklist.md`)

---

## 10. 변경 이력 (커밋 SHA 매핑)

| Phase | OpsConsole 커밋 | Claude-Opus-bluevlad 커밋 |
|-------|----------------|---------------------------|
| P0 부트스트랩 | `df1ec76` ~ `aaa329d` (7 commits) | `fd1cbdd` (전략 문서 신규) |
| P0 잔여 (OAuth + 게이트웨이) | `f64911d` | `690abe5` (infra+registry) |
| P1 (담당자/헬스/Slack) | `72d0561` | `9e7f68f` |
| P2 (GitHub Bridge) | `10d9f6e` | `f21d8e2` |
| P3 (콘텐츠 에디터) | `b24ed46` | `1af2caf` |
| P4 (Tauri 트레이) | `4b00d2c` | `f10933a` |
| P5 (보안 + 운영) | `757c944` | `7dedf36` |

전체 P0~P5: 약 **6주 일정 → 1일 압축 완료** (테스트 114건 / 코드 ~10K LoC).

---

## 11. 진입점 문서 맵

| 목적 | 문서 |
|------|------|
| 새로 합류 — 시스템 파악 (30분) | **이 문서** (`docs/dev/overview.md`) |
| 로컬에서 실행 | [`quickstart.md`](./quickstart.md) |
| DB 셋업 | [`database-setup.md`](./database-setup.md) |
| GitHub Bridge 활성화 | [`github-bridge.md`](./github-bridge.md) |
| 본 서비스 콘텐츠 통합 | [`content-integration.md`](./content-integration.md) |
| Tauri 빌드·서명 | [`tray-build.md`](./tray-build.md) |
| 일일 운영 | [`operations.md`](./operations.md) |
| 사고 대응 | [`runbook.md`](./runbook.md) |
| DB 백업·복구 | [`backup-restore.md`](./backup-restore.md) |
| OWASP 점검 | [`owasp-checklist.md`](./owasp-checklist.md) |
| 전략·플랜·ADR | [`Claude-Opus-bluevlad/services/opsconsole/`](https://github.com/bluevlad/Claude-Opus-bluevlad/tree/main/services/opsconsole) (private) |

---

## 변경 이력

| 날짜 | 변경 |
|------|------|
| 2026-04-30 | 최초 작성 — P0~P5 완료 정리 |
