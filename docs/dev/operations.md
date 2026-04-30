# OpsConsole 운영 가이드

> 운영자 / SRE 가 일상 운영에서 참조하는 절차·체크리스트.

---

## 0. 시스템 구성

```
사용자/운영자/디바이스
        ↓ HTTPS
┌─────────────────┐
│ unmong-gateway  │  Let's Encrypt 와일드카드 *.unmong.com
│ (nginx 1.27)    │  → opsconsole.unmong.com → host.docker.internal:4100/9100
└────────┬────────┘
         │ database-network
┌────────▼─────────────┐    ┌─────────────────────┐
│ opsconsole-frontend  │    │ opsconsole-backend  │
│  vite/nginx :4100    │    │  FastAPI :9100      │
└──────────────────────┘    │  + APScheduler 5분  │
                            └────────┬────────────┘
                                     │
                            ┌────────▼────────┐
                            │ postgresql      │
                            │ opsconsole(_dev)│
                            └─────────────────┘
                                     │
            외부:  GitHub API · Slack Webhook · 본 서비스 polling
```

---

## 1. 정상 가동 확인

### 1.1 1분 헬스 체크

```bash
# 게이트웨이 직접
curl https://opsconsole.unmong.com/api/health
# → {"status":"ok",...}

# 컨테이너 상태
docker ps --filter name=opsconsole --format "table {{.Names}}\t{{.Status}}"

# DB 핑
docker exec -e PGPASSWORD="$DB_SUPERPW" postgresql \
  psql -U postgres -tAc "SELECT 1" -d opsconsole
```

### 1.2 카탈로그·헬스 살펴보기

```bash
# 등록 서비스
curl -sk https://opsconsole.unmong.com/api/catalog/services | jq

# 마지막 헬스 점검 시각 (5분 잡)
docker exec -e PGPASSWORD=$OPSPW postgresql \
  psql -U opsconsole_svc -d opsconsole -tAc \
  "SELECT max(checked_at) FROM ops_health_snapshots"

# 최근 알림 디듀프 상태
docker exec -e PGPASSWORD=$OPSPW postgresql \
  psql -U opsconsole_svc -d opsconsole -tAc \
  "SELECT s.code, a.consecutive_failures, a.resolved_notified, a.last_alerted_at
   FROM ops_alert_state a JOIN ops_sections s ON a.section_id=s.id"
```

---

## 2. 일일 작업

### 2.1 매니페스트 변경 반영

본 서비스(예: AllergyInsight) 의 `ops/manifest.yml` 수정 후:

```bash
# OpsConsole 관리자 JWT 로 sync 트리거
curl -X POST https://opsconsole.unmong.com/api/catalog/sync \
  -H "Authorization: Bearer $OPS_ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{"service_code":"allergyinsight","mode":"github","ref":"main"}'
```

`mode=github` 은 `GITHUB_PAT` 가 필요. 미설정 시 `mode=local` + `local_path` 사용.

### 2.2 헬스 즉시 점검

ops_admin 만:
```bash
curl -X POST https://opsconsole.unmong.com/api/health/probe/run \
  -H "Authorization: Bearer $OPS_ADMIN_JWT"
# → {"processed": N}
```

### 2.3 권한 부여·해제

웹 UI: `/services/{code}/sections/{section}/permissions` (ops_admin)
또는 API:
```bash
curl -X POST https://opsconsole.unmong.com/api/assignments \
  -H "Authorization: Bearer $OPS_ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{"section_id":94,"user_email":"reviewer@example.com","can_publish":true}'
```

---

## 3. 토큰·시크릿 회전 정책

| 시크릿 | 주기 | 대체 방법 |
|--------|------|-----------|
| `JWT_SECRET_KEY` | **분기 1회** | 회전 시 모든 사용자 재로그인 (의도된 동작) |
| `GITHUB_PAT` | 분기 1회 또는 **GitHub App 전환 권장** | fine-grained PAT, 레포·권한 최소화 |
| `GITHUB_WEBHOOK_SECRET` | 연 1회 또는 사고 시 즉시 | OpsConsole `.env` + 각 레포 webhook secret 동시 갱신 |
| `OPS_INTERNAL_TOKEN` | 분기 1회 | OpsConsole + 본 서비스 `.env` 동시 갱신 |
| `SLACK_WEBHOOK_URL` | 연 1회 | 채널 측 Incoming Webhook 재발급 |
| Apple Developer Cert | **매년** ($99 갱신) | Tauri 빌드 영향 |
| Tauri Updater Key | 분실 시 재서명 불가 — **백업 필수** | 1Password / 회사 vault |

회전 시 컨테이너 `--force-recreate` 재시작 필요.

---

## 4. 모니터링·알림

### 4.1 OpsConsole 자체 헬스

`unmong-gateway` 측에서 OpsConsole API 헬스를 외부 모니터링(예: UptimeRobot)에 등록 권장.

### 4.2 Slack 알림 채널

- `#allergy-ops` (1호 고객) — 헬스 실패 + 변경요청 발급 알림
- 알림 디듀프: 3회 연속 실패 + 1h cooldown + 회복 1회 (자세한 정책: `docs/dev/p1-..` 참조)

### 4.3 감사 로그 모니터링

```bash
# 최근 1시간 내 admin 액션
curl -sk "https://opsconsole.unmong.com/api/audit-log?action=permission_granted&limit=20" \
  -H "Authorization: Bearer $OPS_ADMIN_JWT" | jq
```

비정상 패턴(짧은 시간 내 반복 권한 부여 등) 검출 시 사고 대응 런북 §3 참조.

---

## 5. 데이터베이스

### 5.1 마이그레이션 적용

```bash
docker exec -it opsconsole-backend-dev alembic upgrade head
```

### 5.2 스키마 다운그레이드 (1단계)

```bash
docker exec -it opsconsole-backend-dev alembic downgrade -1
```

### 5.3 백업 / 복구

`docs/dev/backup-restore.md` 참조.

---

## 6. 보안 점검 (분기 1회)

`docs/dev/owasp-checklist.md` 참조. 점검 결과는 `ops_audit_log` 또는 별도 인시던트 트래커에 기록.

---

## 7. 배포 절차

1. **메인 브랜치 PR 머지** — GitHub Actions CI (`security.yml`) 모두 그린
2. **백엔드/프런트 컨테이너 재기동** —
   ```bash
   docker compose -f docker-compose.dev.yml up -d --force-recreate
   ```
   alembic upgrade 자동 실행됨.
3. **헬스 검증** — §1.1 절차
4. **5분 후 헬스 잡 동작 확인** — `ops_health_snapshots` 에 신규 행 INSERT 됨

운영 환경의 무중단 배포 (blue/green) 는 단일 backend 컨테이너 구성에서 미적용. 짧은 다운타임(수 초) 허용이 전제.

---

## 8. 트러블슈팅 빠른 가이드

| 증상 | 1차 조치 |
|------|----------|
| `/api/health` 503 | `docker ps` 컨테이너 실행 여부 / `docker logs opsconsole-backend-dev --tail 50` |
| 카탈로그 비어있음 | `python -m scripts.seed_allergyinsight` 시드 또는 `POST /api/catalog/sync` |
| 헬스 잡 동작 안 함 | `APP_DEBUG=true` 로그 확인 / `health_probe_enabled=true` / 컨테이너 시간대 KST 확인 |
| Slack 알림 없음 | `SLACK_WEBHOOK_URL` 비어있음 / 디듀프 cooldown 중 (1h) |
| 콘텐츠 polling 401 | `OPS_INTERNAL_TOKEN` 양 쪽 일치 확인 |
| 디바이스 로그인 410 | user_code 만료(10분) — 다시 init |

심각도 높은 사고는 `docs/dev/runbook.md` 참조.
