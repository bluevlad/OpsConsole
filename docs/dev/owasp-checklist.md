# OWASP Top 10 자가 점검 체크리스트 (P5)

> 분기 1회 수행. 결과는 `reports/security-YYYY-Q.md` 또는 인시던트 트래커에 기록.

---

## A01 Broken Access Control ✅

- [x] 모든 API 엔드포인트가 `Depends(get_current_user)` 또는 `require_role(...)` 사용
- [x] 역할 매트릭스 (P5 §1) 준수: viewer < member < reviewer < admin
- [x] section permission (`can_edit_content` / `can_publish`) 화이트리스트 검사
- [x] internal endpoint 는 `X-Ops-Internal-Token` 별도 인증 (사용자 JWT 미사용)

검증 방법:
```bash
# member 토큰으로 admin 전용 호출 → 403 기대
curl -H "Authorization: Bearer $MEMBER_JWT" \
  https://opsconsole.unmong.com/api/audit-log
# → 403
```

## A02 Cryptographic Failures 🟡

- [x] TLS — `unmong-gateway` Let's Encrypt 와일드카드, HSTS 헤더 적용
- [x] JWT HS256 (현재) — RS256 전환은 키 관리 인프라 필요 (P5+ 후속)
- [x] DB 비밀번호 환경변수, 코드 미하드코딩
- [x] 민감 정보 마스킹 (audit log, 로그 출력)
- [⏳] JWT secret rotation 자동화 — 분기 수동, 자동화는 P5+ 후속

## A03 Injection ✅

- [x] SQLAlchemy ORM 만 사용 — raw SQL 파라미터는 named binding (`text(":foo")`)
- [x] Pydantic 검증 (모든 request body)
- [x] 매니페스트 yaml 은 `yaml.safe_load`
- [x] HTML 콘텐츠는 client-side `DOMPurify`
- [x] format='html' 비활성 (`assert_writable`)

## A04 Insecure Design ✅

- [x] 콘텐츠 블록 — 화이트리스트 기반 (`fetch_block_spec`)
- [x] section assets — 매니페스트가 SSoT, 임의 추가 금지
- [x] 변경요청 status 전이 ops_admin 전용
- [x] device_code — 한 번만 redeem, expiry 10분

## A05 Security Misconfiguration ✅

- [x] CORS allow_origins 명시적 화이트리스트 (`configure_cors`)
- [x] CSP / X-Frame-Options / X-Content-Type-Options / Referrer-Policy 헤더 (P5 §3)
- [x] HSTS (운영 환경)
- [x] `X-Powered-By` 미노출 (FastAPI 기본)
- [x] FastAPI debug=False (운영)
- [x] `.gitignore` — `.env`, secrets

## A06 Vulnerable Components ✅

- [x] `pip-audit` GitHub Actions 주간 스캔 (`security.yml`)
- [x] `npm audit` (frontend + tray) 주간
- [x] `bandit` Python static analysis 주간

수동 점검:
```bash
cd backend && pip-audit --requirement requirements.txt
cd frontend && npm audit --omit=dev
cd tray && npm audit --omit=dev
```

## A07 Auth Failures 🟡

- [x] Google OAuth ID token 검증 (audience + issuer + email_verified)
- [x] JWT exp 검증 (12h)
- [x] Bearer 미존재/잘못된 형식 → 401
- [⏳] 로그인 실패 횟수 제한 — Google 측에서 처리. OpsConsole 자체 PIN/Password 흐름 없음
- [x] device_code 한 번 redeem 후 무효
- [x] device_code expiry 10분

## A08 Data Integrity ✅

- [x] GitHub webhook HMAC-SHA256 검증
- [x] webhook idempotency (`X-GitHub-Delivery` → `ops_change_request_events.github_event_id`)
- [x] audit log append-only (UPDATE/DELETE 없음)
- [x] alembic 마이그레이션 — 버전 관리

## A09 Logging Failures ✅

- [x] 모든 인증 이벤트 — `user_created` / `user_login` / `device_approved` / `device_redeemed`
- [x] 모든 권한 변경 — `permission_granted` / `permission_updated` / `permission_revoked`
- [x] 콘텐츠 워크플로 — `content_draft_saved` / `_review_requested` / `_approved_and_published` / `_rejected` / `_published_direct`
- [x] 변경요청 — `change_request_created` / `change_request_patched`
- [x] webhook — `github_webhook` (event + action)
- [x] 매니페스트 sync — `sync_manifest`
- [x] audit log 마스킹 (이메일 / 토큰)

## A10 SSRF ✅

- [x] 매니페스트 `health.url` 검증 (`assert_safe_probe_url`)
  - 사설 IP / loopback / link-local 차단
  - http(s) 외 스킴 차단 (file/gopher/ftp)
  - DNS 재바인딩 방어 (hostname → IP resolve 후 사설 IP 차단)
- [x] GitHub API 호출 — host 고정 (`api.github.com`)
- [x] Slack webhook — 단일 환경변수, 사용자 입력 미반영

dev 환경 우회: `HEALTH_PROBE_ALLOW_PRIVATE=true` (운영 환경에선 절대 false)

---

## 점검 완료 양식

```markdown
# OWASP 점검 — YYYY-Q

| 항목 | 상태 | 비고 |
|------|------|------|
| A01 | ✅ | ... |
| A02 | 🟡 | RS256 전환 검토 필요 |
| ... | ... | ... |

## 후속 조치
- [ ] ...
```

`reports/security-YYYY-Q.md` 에 저장 + Slack `#allergy-ops` 공유.
