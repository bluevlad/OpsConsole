# Database Setup — opsconsole / opsconsole_dev

> 공유 PostgreSQL 컨테이너(`postgresql`, `pgvector/pgvector:pg15`)에 OpsConsole 전용 DB·계정을 생성한다.
> **본 작업은 운영 DB에 영향을 줄 수 있으므로 반드시 수동 검토 후 실행.**

## 사전 확인

```bash
# 컨테이너 동작 확인
docker ps --filter name=postgresql --format "{{.Status}}"
# → Up XXh (healthy)

# 슈퍼유저 접속 확인 (무중단)
docker exec -e PGPASSWORD='pgs8MbcmFsKC6Hcxc37g66Ovu28hdJg' postgresql \
  psql -U postgres -tAc "SELECT version();"
```

## 생성 SQL

[`./database-init.sql`](./database-init.sql) 파일에 정리되어 있다.

요약:
- 서비스 계정: `opsconsole_svc` (다른 서비스의 `*_svc` 컨벤션과 동일)
- DB: `opsconsole`(prod), `opsconsole_dev`(dev)
- prod·dev 모두 동일 계정에 ALL 권한 부여
- 테이블 prefix는 `ops_` (마이그레이션에서 강제)

## 실행 절차

### 1) 비밀번호 생성

```bash
# 32자 random (URL-safe). 결과를 .env의 DATABASE_URL 비밀번호 자리에 붙여넣을 것
python3 -c "import secrets; print(secrets.token_urlsafe(24))"
```

생성한 비밀번호를 다음 두 곳에 적용:

1. `database-init.sql` 안의 `CHANGE_ME_PASSWORD` 두 곳을 동일 값으로 치환
2. 프로젝트 루트 `.env` 의 `DATABASE_URL` 비밀번호 자리

> ⚠️ 비밀번호는 **절대 커밋하지 말 것**. `.env`는 `.gitignore` 등재됨.

### 2) SQL 실행 (검토 후 실행)

```bash
docker exec -i -e PGPASSWORD='pgs8MbcmFsKC6Hcxc37g66Ovu28hdJg' postgresql \
  psql -U postgres -v ON_ERROR_STOP=1 < docs/dev/database-init.sql
```

### 3) pg_hba.conf 권한 항목 추가 (서비스 계정 접속 허용)

공유 PostgreSQL은 `pg_hba.conf`에서 서비스 계정별로 접속 가능 DB·CIDR을 화이트리스트한다. opsconsole 항목을 추가해야 한다.

```bash
# ① 백업
docker exec postgresql sh -c \
  'cp /var/lib/postgresql/data/pg_hba.conf \
       /var/lib/postgresql/data/pg_hba.conf.bak.opsconsole-$(date +%Y%m%d-%H%M%S)'

# ② reject all 라인 앞에 OpsConsole 규칙 4줄 삽입
docker exec postgresql sh -c '
awk "
BEGIN { inserted=0 }
/^host[[:space:]]+all[[:space:]]+all[[:space:]]+0\.0\.0\.0\/0[[:space:]]+reject/ && !inserted {
  print \"# OpsConsole (added 2026-04-30) — services/opsconsole/\"
  print \"host    opsconsole          opsconsole_svc      192.168.0.0/16      scram-sha-256\"
  print \"host    opsconsole_dev      opsconsole_svc      192.168.0.0/16      scram-sha-256\"
  print \"host    opsconsole          opsconsole_svc      172.30.0.0/16       scram-sha-256\"
  print \"host    opsconsole_dev      opsconsole_svc      172.30.0.0/16       scram-sha-256\"
  print \"\"
  inserted=1
}
{ print }
" /var/lib/postgresql/data/pg_hba.conf > /tmp/pg_hba.new \
  && mv /tmp/pg_hba.new /var/lib/postgresql/data/pg_hba.conf \
  && chown postgres:postgres /var/lib/postgresql/data/pg_hba.conf \
  && chmod 600 /var/lib/postgresql/data/pg_hba.conf'

# ③ Reload (무중단 — 기존 연결 영향 없음)
docker exec -e PGPASSWORD='SUPERUSER_PW' postgresql \
  psql -U postgres -tAc "SELECT pg_reload_conf();"
# → t
```

> ⚠️ 새 규칙은 반드시 `host all all 0.0.0.0/0 reject` **앞에** 들어가야 한다. 매칭은 위→아래 순서.

### 4) 검증

```bash
# DB 2개 생성 확인
docker exec -e PGPASSWORD='pgs8MbcmFsKC6Hcxc37g66Ovu28hdJg' postgresql \
  psql -U postgres -tAc "SELECT datname FROM pg_database WHERE datname LIKE 'opsconsole%' ORDER BY datname;"
# → opsconsole
# → opsconsole_dev

# 계정 생성 확인
docker exec -e PGPASSWORD='pgs8MbcmFsKC6Hcxc37g66Ovu28hdJg' postgresql \
  psql -U postgres -tAc "SELECT rolname FROM pg_roles WHERE rolname='opsconsole_svc';"
# → opsconsole_svc

# 신규 계정으로 dev DB 접속 (비밀번호는 위에서 생성한 값)
docker exec -e PGPASSWORD='YOUR_GENERATED_PASSWORD' postgresql \
  psql -U opsconsole_svc -d opsconsole_dev -tAc "SELECT current_user, current_database();"
# → opsconsole_svc|opsconsole_dev
```

## 롤백 (필요 시)

```sql
-- 주의: 데이터까지 모두 삭제됨
DROP DATABASE IF EXISTS opsconsole;
DROP DATABASE IF EXISTS opsconsole_dev;
DROP USER IF EXISTS opsconsole_svc;
```

## 다음 단계

DB·계정 생성 후 → P0 §1 alembic 초기 마이그레이션 (6개 테이블 생성):

```bash
cd backend
alembic upgrade head
```

(alembic 설정은 `alembic.ini` + `app/database/migrations/`에 작성 예정 — Task #3)
