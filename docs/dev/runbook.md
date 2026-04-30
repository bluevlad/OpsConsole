# OpsConsole 사고 대응 런북

> 심각한 사고 발생 시 단계별 대응 절차. 침착하게 위에서부터.

---

## SEV 등급

| Level | 정의 | 1차 대응시간 | 통보 |
|-------|------|--------------|------|
| **SEV-1** | OpsConsole 전체 다운 / 토큰 노출 의심 / DB 손상 | 즉시 | Slack `#allergy-ops` + 운영자 직접 콜 |
| **SEV-2** | 일부 기능 장애 (헬스 잡 / Slack 알림 / GitHub Bridge) | 30분 | Slack |
| **SEV-3** | 단일 섹션 콘텐츠 게시 실패 / UI 버그 | 1일 | GitHub Issue |

---

## RB-01: SEV-1 토큰/시크릿 유출 의심

증상 예: gitleaks CI 가 `OPS_INTERNAL_TOKEN` / `JWT_SECRET_KEY` / `GITHUB_PAT` 등 검출.

### 1. 즉시 격리 (5분 내)
- 해당 시크릿을 운영 환경에서 무효화 (회전):
  - `JWT_SECRET_KEY` 새로 발급 → `.env` 갱신 → `docker compose up -d --force-recreate opsconsole-backend`
    - **모든 사용자 재로그인 발생** — 의도된 부작용
  - `GITHUB_PAT` → GitHub Settings → Personal access tokens → Revoke → 새 토큰 발급
  - `GITHUB_WEBHOOK_SECRET` → 양 쪽(OpsConsole + 각 레포 webhook 설정) 동시 갱신
  - `OPS_INTERNAL_TOKEN` → OpsConsole + 본 서비스 `.env` 양 쪽 동시 갱신
- 노출된 커밋 push 됐다면 강제 history rewrite + force-push (다른 작업자 영향 큼, SEV-1 만)

### 2. 영향 분석 (30분 내)
- `ops_audit_log` 에서 의심 시점 이후 모든 쓰기 작업 조회:
  ```bash
  curl "https://opsconsole.unmong.com/api/audit-log?limit=500" \
    -H "Authorization: Bearer $NEW_OPS_ADMIN_JWT" | jq '.[] | select(.at > "2026-04-30")'
  ```
- 비정상 패턴: 짧은 시간 내 반복 `permission_granted`, 알 수 없는 IP 의 `device_redeemed`
- GitHub Audit Log: https://github.com/organizations/bluevlad/settings/audit-log

### 3. 폐기 (1시간 내)
- 노출된 시크릿이 유효했던 기간의 모든 GitHub Issue 검토
- 노출 가능성 높은 콘텐츠 게시본 일시 archive (status='archived')
- 사고 보고서 작성 (`reports/incident-YYYY-MM-DD.md`)

---

## RB-02: SEV-1 OpsConsole 전체 다운

### 1. 분류 (3분)

```bash
# 게이트웨이부터 차례로
curl -I https://opsconsole.unmong.com/                  # 1. nginx 살아있나
curl https://opsconsole.unmong.com/api/health           # 2. backend 응답하나
docker ps --filter name=opsconsole                       # 3. 컨테이너 상태
docker logs opsconsole-backend-dev --tail 50             # 4. 백엔드 로그
docker exec postgresql pg_isready -U postgres            # 5. DB 응답
```

### 2. 흔한 원인 + 빠른 복구

| 원인 | 복구 |
|------|------|
| backend OOM / panic | `docker compose -f docker-compose.dev.yml restart opsconsole-backend` |
| DB 연결 풀 고갈 | DB 상 `SELECT count(*) FROM pg_stat_activity` 후 long-running 종료 |
| pg_hba.conf rejects | `docs/dev/database-setup.md §3` 항목 잔존 확인, reload |
| nginx 게이트웨이 conf 망가짐 | `docker exec unmong-gateway nginx -t` 검증, 직전 백업 복원 |
| host 디스크 가득 | `df -h` 확인, docker prune |
| alembic 부분 적용 (스키마 불일치) | `alembic current` 확인, `alembic downgrade -1` 후 코드 롤백 |

### 3. 조치 후 검증

```bash
curl https://opsconsole.unmong.com/api/health
curl https://opsconsole.unmong.com/api/catalog/services -H "Authorization: Bearer $JWT"
```

---

## RB-03: SEV-2 헬스 잡 미동작

증상: `ops_health_snapshots` 에 최근 5분 내 row 없음.

```bash
# scheduler 로그
docker logs opsconsole-backend-dev | grep -i scheduler

# 잡 수동 실행
curl -X POST https://opsconsole.unmong.com/api/health/probe/run \
  -H "Authorization: Bearer $OPS_ADMIN_JWT"
```

원인 후보:
- `HEALTH_PROBE_ENABLED=false` `.env` 확인
- timezone 불일치 — `APP_TZ=Asia/Seoul` 확인
- APScheduler 단일 인스턴스 보장 — `max_instances=1` 코드 확인
- 외부 호스트 다운 — 본 서비스 게이트웨이 응답 확인 (`curl -I https://allergy.unmong.com/admin`)

---

## RB-04: SEV-2 GitHub Bridge 미동작

증상 1: 변경요청 폼 제출했는데 GitHub Issue 미발급.
- backend 로그에 `GitHub issue 발급 실패` 검색
- `GITHUB_PAT` 만료 / 권한 부족 (issues:write 필요) 가능성
- GitHub API rate limit (5000/h) 초과 가능성 — `X-RateLimit-Remaining` 응답 헤더

증상 2: PR 머지했는데 OpsConsole status 안 바뀜.
- 해당 레포 → Settings → Webhooks → Recent Deliveries 에서 최근 이벤트 응답 확인
- 401 invalid X-Hub-Signature-256 → secret 불일치, §RB-01 회전 절차 일부
- 200 no_match → PR body 의 `Closes #N` 키워드 미작성. 본문 수정 후 webhook redeliver

---

## RB-05: SEV-2 Slack 알림 폭주

3회 연속 실패가 정상이지만 **Cool down 무력화** 또는 **상태 미반영** 시 알림 폭주 가능.

### 즉시 차단

```bash
# .env 에서 SLACK_WEBHOOK_URL 비우기 + 컨테이너 재기동
echo "SLACK_WEBHOOK_URL=" >> .env  # 비활성
docker compose -f docker-compose.dev.yml up -d --force-recreate opsconsole-backend
```

### 원인 분석

```bash
# alert state 확인
docker exec -e PGPASSWORD=$OPSPW postgresql \
  psql -U opsconsole_svc -d opsconsole -c \
  "SELECT s.code, a.consecutive_failures, a.last_alerted_at, a.resolved_notified
   FROM ops_alert_state a JOIN ops_sections s ON a.section_id=s.id
   WHERE a.last_alerted_at > now() - interval '1 hour'"
```

cooldown 1h 무시되면 코드 버그 — `app/notify/alert_router.py` 회귀 테스트 (`test_cooldown_suppresses_repeat_alert`) 재실행.

---

## RB-06: SEV-3 콘텐츠 게시 후 본 서비스 미반영

원인 후보 + 조치:
1. 본 서비스 polling client 가 `OPS_INTERNAL_TOKEN` 잘못된 값
2. 본 서비스 캐시가 ETag 304 만 받고 있음 — 강제 갱신
3. 매니페스트의 `content_blocks` 화이트리스트에 key 미등록

```bash
# OpsConsole 측에서 확인
curl -H "X-Ops-Internal-Token: $TOKEN" \
  "https://opsconsole.unmong.com/api/internal/content/published?service=allergyinsight"
```

본 서비스 측에서 polling 강제 트리거하거나 캐시 비우고 재시작.

---

## 사고 보고서 템플릿

```markdown
# Incident YYYY-MM-DD

## 요약
- SEV: 1 / 2 / 3
- 발생: YYYY-MM-DD HH:MM KST
- 복구: YYYY-MM-DD HH:MM KST  (총 N분)
- 영향: 사용자 N명 / 섹션 N개 / ...

## 타임라인
- HH:MM 증상 첫 보고
- HH:MM 분류
- HH:MM 1차 조치
- HH:MM 복구

## 원인 (5 Whys)
1. ...
2. ...

## 후속 조치
- [ ] 회귀 테스트 추가 (해당 시나리오)
- [ ] 모니터링 보강
- [ ] 런북 업데이트
```
