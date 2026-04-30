# Quickstart — 로컬에서 OpsConsole 띄우기

> 본 가이드는 **이미 공유 PostgreSQL 컨테이너(`postgresql`)가 운영 중**임을 전제로 한다.
> 처음이면 [`database-setup.md`](./database-setup.md) 를 먼저 실행해 OpsConsole DB·계정·pg_hba 항목을 준비하라.

---

## 0. 사전 조건

| 항목 | 요구 |
|------|------|
| Docker | 24+ |
| Docker Compose | v2+ |
| 공유 PostgreSQL | `postgresql` 컨테이너 실행 중, `database-network` 외부 네트워크 존재 |
| OpsConsole DB | `opsconsole_dev` + `opsconsole_svc` 계정 ([database-setup.md](./database-setup.md)) |
| pg_hba 항목 | `opsconsole_svc` 의 192.168.0.0/16 / 172.30.0.0/16 허용 |

호스트(직접) 실행 추가 요구:

| 항목 | 요구 |
|------|------|
| Python | 3.11 또는 3.12 (3.14는 pydantic-core PyO3 미지원 — venv 생성 시 명시 필요) |
| Node.js | 20+ |
| npm | 10+ |

---

## 1. 환경변수

```bash
cp .env.example .env
# .env 안의 비밀번호·시크릿을 교체:
# - DATABASE_URL 의 비밀번호 (database-setup.md 에서 생성한 값)
# - JWT_SECRET_KEY (P0 §2 auth 진입 전 강한 랜덤 값으로)
# - GOOGLE_OAUTH_*, GITHUB_PAT, SLACK_WEBHOOK_URL : P0 §2/P1/P2 단계에서 채움
```

---

## 2. 실행 (Docker compose, 권장)

```bash
docker compose -f docker-compose.dev.yml up --build
```

자동으로 수행되는 것:
1. backend 컨테이너 — `pip install -r requirements.txt` (캐시 volume 사용)
2. backend 컨테이너 — `alembic upgrade head` (스키마 최신화)
3. backend 컨테이너 — `uvicorn --reload` (포트 9100)
4. frontend 컨테이너 — `npm install` (캐시 volume) + `vite dev` (포트 4100)
5. 두 컨테이너 모두 `database-network` 외부 네트워크에 합류 (postgresql 컨테이너로 DNS 통신)

확인:

```bash
curl http://localhost:9100/api/health           # → {"status":"ok",...}
curl http://localhost:4100/api/health           # → vite proxy 경유, 동일 응답
curl http://localhost:4100/api/catalog/services # → AllergyInsight (시드 적재 후)
open  http://localhost:4100                     # → React 카탈로그 UI
```

종료:

```bash
docker compose -f docker-compose.dev.yml down
```

볼륨까지 삭제 (pip / npm 캐시 초기화):

```bash
docker compose -f docker-compose.dev.yml down -v
```

---

## 3. 실행 (호스트 직접 — 디버깅 용도)

### 3.1 backend

```bash
cd backend
python3.12 -m venv .venv          # 또는 python3.11
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head              # opsconsole_dev 스키마 최신화
uvicorn app.main:app --host 0.0.0.0 --port 9100 --reload
```

### 3.2 frontend

```bash
cd frontend
npm install
npm run dev                       # → http://localhost:4100
```

`vite.config.js` 의 proxy target 은 기본적으로 `localhost:9100` 이라 호스트 직접 실행 시 그대로 동작한다.

---

## 4. 초기 시드 — AllergyInsight 11섹션

처음 띄운 직후엔 카탈로그가 비어있다. 시드 CLI로 적재:

```bash
# 호스트(venv 활성화 상태)
cd backend
python -m scripts.seed_allergyinsight

# 또는 backend 컨테이너 안에서
docker exec -it opsconsole-backend-dev python -m scripts.seed_allergyinsight
```

출력 예:

```
[seed] service=allergyinsight sections=11
[seed] created=True
[seed] added=  ['ai-consult', 'ai-insight', 'analytics', ...]
[seed] snapshot_id=22
```

API 검증:

```bash
curl http://localhost:9100/api/catalog/services
curl http://localhost:9100/api/catalog/services/allergyinsight/sections
curl http://localhost:9100/api/catalog/services/allergyinsight/sections/ai-consult
```

브라우저: `http://localhost:4100/services` → AllergyInsight 카드 → 11섹션 표 → ai-consult 자산 8행.

---

## 5. 테스트

```bash
cd backend
source .venv/bin/activate
pytest                            # 38 케이스 (health/manifest/sync/catalog API)
```

```bash
cd frontend
npm run build                     # vite production 빌드 검증
```

---

## 6. 자주 발생하는 이슈

| 증상 | 원인 / 조치 |
|------|------------|
| `password authentication failed for user "opsconsole_svc"` | `.env` 의 DATABASE_URL 비밀번호가 `database-init.sql` 실행 시 사용한 값과 다름 |
| `pg_hba.conf rejects connection` | pg_hba 에 opsconsole 항목이 없거나 reject 라인 뒤에 있음. [database-setup.md §3](./database-setup.md#3-pg_hbaconf-권한-항목-추가-서비스-계정-접속-허용) 참조 |
| `network database-network not found` | `database-services/docker-compose.yml` 가 먼저 `up` 되어야 함. 또는 `docker network create database-network` 후 postgresql 컨테이너를 그 네트워크에 attach |
| Vite 컨테이너에서 `/api/* → 500` | proxy target 이 `localhost:9100` 으로 잘못 설정. `VITE_PROXY_TARGET=http://opsconsole-backend:9100` 환경변수 확인 |
| `pydantic-core` 빌드 실패 (`PyO3 supports max Python 3.13`) | Python 3.14 사용. venv 를 3.11/3.12 로 재생성 |
| `email-validator is not installed` | `pip install email-validator==2.2.0` (`requirements.txt` 최신화 후 재설치) |

---

## 7. 정리·재시작

```bash
# 백엔드만 재시작 (코드 변경 후 hot-reload 가 안 잡혔을 때)
docker compose -f docker-compose.dev.yml restart opsconsole-backend

# DB 스키마 다시 만들기 (전체 데이터 삭제!)
docker exec -it opsconsole-backend-dev alembic downgrade base
docker exec -it opsconsole-backend-dev alembic upgrade head
docker exec -it opsconsole-backend-dev python -m scripts.seed_allergyinsight
```

---

## 8. 다음 단계

- P0 §3 React 카탈로그 UI 는 read-only — 인증 없이 노출. P5 단계에서 `ops_admin` JWT gate 추가.
- 매니페스트 업데이트 자동 sync (cron 또는 GitHub webhook)는 P2 GitHub Bridge.
- 헬스 체크 잡(5분 주기 + Slack 알림)은 P1.

전략·플랜 정본: [`Claude-Opus-bluevlad/services/opsconsole/`](https://github.com/bluevlad/Claude-Opus-bluevlad/tree/main/services/opsconsole) (private)
