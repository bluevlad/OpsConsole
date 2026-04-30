-- =============================================================================
-- OpsConsole — DB / 서비스 계정 초기화
-- 실행 위치: postgresql 컨테이너 (슈퍼유저 postgres)
-- 실행 방법: docs/dev/database-setup.md 참조
-- =============================================================================

-- 1) 서비스 계정 생성 (이미 존재하면 무시)
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'opsconsole_svc') THEN
    CREATE USER opsconsole_svc WITH PASSWORD 'CHANGE_ME_PASSWORD';
  END IF;
END $$;

-- 2) DB 생성 — 운영
SELECT 'CREATE DATABASE opsconsole OWNER opsconsole_svc'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'opsconsole')\gexec

-- 3) DB 생성 — 개발
SELECT 'CREATE DATABASE opsconsole_dev OWNER opsconsole_svc'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'opsconsole_dev')\gexec

-- 4) 권한 — 운영
GRANT ALL PRIVILEGES ON DATABASE opsconsole     TO opsconsole_svc;
GRANT ALL PRIVILEGES ON DATABASE opsconsole_dev TO opsconsole_svc;

-- 5) public 스키마 권한 (PG 15+: public 스키마는 기본적으로 owner만 사용 가능)
\c opsconsole
GRANT ALL ON SCHEMA public TO opsconsole_svc;

\c opsconsole_dev
GRANT ALL ON SCHEMA public TO opsconsole_svc;

-- 6) 검증 메시지
\c postgres
SELECT
  (SELECT string_agg(datname, ', ') FROM pg_database WHERE datname LIKE 'opsconsole%') AS databases,
  (SELECT rolname FROM pg_roles WHERE rolname = 'opsconsole_svc') AS service_account;
