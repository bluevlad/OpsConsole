# DB 백업·복구 절차

> OpsConsole `opsconsole` / `opsconsole_dev` PostgreSQL DB 백업·복구.

---

## 0. 정책

| 항목 | 정책 |
|------|------|
| 백업 주기 | 매일 03:00 KST (cron) |
| 보존 | 일일 14일 + 주간 12주 + 월간 12개월 |
| 저장 위치 | 호스트 `/Users/rainend/DockerData/backup/opsconsole/` (1차) + S3/외부 (선택) |
| 복구 RTO | 1시간 |
| 복구 RPO | 24시간 (일일 백업) — 분 단위 RPO 필요 시 WAL 아카이빙 검토 |

---

## 1. 수동 백업 (즉시)

```bash
TS=$(date +%Y%m%d-%H%M%S)
DEST=/Users/rainend/DockerData/backup/opsconsole/manual

mkdir -p "$DEST"

docker exec -e PGPASSWORD=pgs8MbcmFsKC6Hcxc37g66Ovu28hdJg postgresql \
  pg_dump -U postgres -d opsconsole --format=custom \
  > "$DEST/opsconsole-$TS.dump"

# 크기 확인
ls -lh "$DEST"/opsconsole-$TS.dump
```

`--format=custom` 은 `pg_restore` 가 빠르게 복원할 수 있는 바이너리 포맷.

---

## 2. 자동 백업 (cron)

`/Users/rainend/DockerData/backup/opsconsole/backup.sh`:

```bash
#!/bin/bash
set -euo pipefail

DEST=/Users/rainend/DockerData/backup/opsconsole/daily
TS=$(date +%Y%m%d)
KEEP_DAYS=14

mkdir -p "$DEST"

docker exec -e PGPASSWORD="$PGPASSWORD" postgresql \
  pg_dump -U postgres -d opsconsole --format=custom \
  > "$DEST/opsconsole-$TS.dump"

# 14일 초과 백업 삭제
find "$DEST" -name 'opsconsole-*.dump' -mtime +$KEEP_DAYS -delete

# 매주 일요일은 weekly 디렉토리에도 복사 (12주 보존)
if [ "$(date +%u)" = "7" ]; then
  WEEKLY=/Users/rainend/DockerData/backup/opsconsole/weekly
  mkdir -p "$WEEKLY"
  cp "$DEST/opsconsole-$TS.dump" "$WEEKLY/"
  find "$WEEKLY" -name 'opsconsole-*.dump' -mtime +84 -delete
fi
```

crontab:
```
0 3 * * *   PGPASSWORD=... bash /Users/rainend/DockerData/backup/opsconsole/backup.sh >> /var/log/opsconsole-backup.log 2>&1
```

macOS launchd 예시는 `database-services/backup.sh` 패턴 참고.

---

## 3. 복구 (전체)

⚠️ **운영 DB 위에 그대로 복원하면 기존 데이터 덮어쓰기**. 반드시 사전에 현재 상태 백업 후 진행.

```bash
# 1. 현재 상태 비상 백업
docker exec -e PGPASSWORD=$DB_SUPERPW postgresql \
  pg_dump -U postgres -d opsconsole --format=custom \
  > /tmp/opsconsole-pre-restore-$(date +%s).dump

# 2. 컨테이너 정지 (다른 클라이언트 차단)
docker compose -f docker-compose.dev.yml stop opsconsole-backend

# 3. 기존 DB drop + recreate
docker exec -e PGPASSWORD=$DB_SUPERPW postgresql psql -U postgres <<SQL
  DROP DATABASE opsconsole;
  CREATE DATABASE opsconsole OWNER opsconsole_svc;
  GRANT ALL PRIVILEGES ON DATABASE opsconsole TO opsconsole_svc;
SQL

# 4. 복원
docker exec -i -e PGPASSWORD=$DB_SUPERPW postgresql \
  pg_restore -U postgres -d opsconsole --no-owner --no-privileges \
  < /Users/rainend/DockerData/backup/opsconsole/daily/opsconsole-YYYYMMDD.dump

# 5. public 스키마 권한 재부여
docker exec -e PGPASSWORD=$DB_SUPERPW postgresql \
  psql -U postgres -d opsconsole -c "GRANT ALL ON SCHEMA public TO opsconsole_svc"

# 6. 컨테이너 재가동
docker compose -f docker-compose.dev.yml start opsconsole-backend

# 7. 검증
curl https://opsconsole.unmong.com/api/health
curl -H "Authorization: Bearer $JWT" https://opsconsole.unmong.com/api/catalog/services
```

---

## 4. 복구 (특정 테이블만)

`pg_restore` 의 `--table` 옵션:

```bash
docker exec -i -e PGPASSWORD=$DB_SUPERPW postgresql \
  pg_restore -U postgres -d opsconsole \
  --table=ops_change_requests --table=ops_change_request_events \
  --no-owner --no-privileges \
  --data-only \
  < backup.dump
```

`--data-only` 는 스키마 유지하고 데이터만 복원. FK 종속성 주의.

---

## 5. 매니페스트 스냅샷 복구

`ops_manifest_snapshots` 가 살아있다면 카탈로그 시드 자체는 매니페스트로 재생성 가능:

```bash
cd backend
.venv/bin/python -m scripts.seed_allergyinsight \
  --manifest tests/fixtures/allergyinsight-manifest.yml \
  --ref restore-$(date +%Y%m%d)
```

또는 GitHub 의 `prod` 브랜치 매니페스트로:
```bash
curl -X POST https://opsconsole.unmong.com/api/catalog/sync \
  -H "Authorization: Bearer $OPS_ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{"service_code":"allergyinsight","mode":"github","ref":"prod"}'
```

---

## 6. 백업 검증 (월 1회)

별도 환경에 복원 → 핵심 쿼리 동작 확인:

```bash
# 임시 DB 생성 + 복원
docker exec -e PGPASSWORD=$DB_SUPERPW postgresql psql -U postgres -c \
  "CREATE DATABASE opsconsole_restore_test OWNER opsconsole_svc"

docker exec -i -e PGPASSWORD=$DB_SUPERPW postgresql \
  pg_restore -U postgres -d opsconsole_restore_test --no-owner \
  < /Users/rainend/DockerData/backup/opsconsole/daily/opsconsole-YYYYMMDD.dump

# 행 수 검증
docker exec -e PGPASSWORD=$DB_SUPERPW postgresql psql -U postgres -d opsconsole_restore_test -c \
  "SELECT 'services', count(*) FROM ops_services
   UNION ALL SELECT 'sections', count(*) FROM ops_sections
   UNION ALL SELECT 'snapshots', count(*) FROM ops_manifest_snapshots"

# 검증 후 삭제
docker exec -e PGPASSWORD=$DB_SUPERPW postgresql psql -U postgres -c \
  "DROP DATABASE opsconsole_restore_test"
```
