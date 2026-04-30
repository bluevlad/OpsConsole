# OpsConsole 프로젝트 설정

> Git-First Workflow는 `~/GIT/CLAUDE.md`에서 자동 상속됩니다.
> 본 파일에는 OpsConsole 고유 설정만 작성합니다.
>
> **전략·플랜·ADR 정본**: [`Claude-Opus-bluevlad/services/opsconsole/`](https://github.com/bluevlad/Claude-Opus-bluevlad/tree/main/services/opsconsole) (private)
> 본 코드 저장소(public)에는 **구현 코드만** 둡니다.

## 프로젝트 개요

- **프로젝트명**: OpsConsole
- **설명**: 멀티 서비스 운영 콘솔 (Internal Developer Portal) — 카탈로그·담당자·콘텐츠·헬스·변경요청 통합 관리
- **GitHub**: https://github.com/bluevlad/OpsConsole (public)
- **상태**: P0 부트스트랩 진행 중
- **1호 고객**: AllergyInsight (`allergy.unmong.com`)

## 기술 스택

- **Backend**: Python 3.10+ + FastAPI + SQLAlchemy 2.0 (asyncpg)
- **Frontend**: React 18 + Vite + React Router 6
- **Database**: PostgreSQL 15 (공유 컨테이너) — DB `opsconsole`/`opsconsole_dev`, prefix `ops_`
- **Auth**: Google OAuth 2.0 + JWT (AllergyInsight와 분리된 클라이언트)
- **Desktop Agent (P4)**: Tauri (Rust + WebView)
- **External**: GitHub REST API, Slack Webhook, SMTP

## 포트 / 도메인

- Frontend: **4100**
- Backend: **9100**
- 도메인: `https://opsconsole.unmong.com/` (게이트웨이)
- `https://도메인:포트` 형식 금지 — Claude-Opus-bluevlad의 `standards/infrastructure/DOMAIN_MANAGEMENT.md` 준수

## 개발 환경

### 빌드 및 실행

```bash
# Backend (직접)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 9100 --reload

# Frontend (직접)
cd frontend
npm install
npm run dev      # → http://localhost:4100

# Docker 통합 (권장)
docker compose -f docker-compose.dev.yml up --build
```

### 테스트

```bash
# Backend
cd backend && pytest

# Frontend
cd frontend && npm test
```

## 프로젝트별 규칙

### 브랜치 전략
- 기본 브랜치: `main`
- 기능 작업: `feature/{phase}-{short-title}` (예: `feature/p0-manifest-parser`)
- 핫픽스: `fix/{short-title}`

### 코드 스타일
- Python: ruff + black (line-length 100)
- JS/TS: Prettier + ESLint (Vite 기본)

### 작업 시 주의사항

1. **본 서비스(AllergyInsight 등) 침습 최소화** — 다른 서비스 레포에는 `ops/manifest.yml` 파일 1개만 추가. 그 외 코드 변경 금지.
2. **운영 권한 분리** — OpsConsole의 `ops_admin`은 본 서비스의 `super_admin`과 별도 계정 모델. JWT 공유 절대 금지.
3. **매니페스트 스키마 변경 금지** — 정본은 Claude-Opus-bluevlad `standards/ops-console/manifest-schema.yml`. 후방 호환만 허용 (필드 추가 ✅ / 삭제·이름 변경 ❌).
4. **Phase 진행 순서 준수** — P0(읽기전용)이 끝나기 전에 P3(콘텐츠 에디터)로 점프 금지.
5. **시크릿 절대 커밋 금지** — `.env`, `*.pem`, `service-account*.json`, Tauri 서명 키 등은 `.gitignore` 등재 확인.
6. **전략 문서 작성 위치** — 의사결정·분석·플랜·로드맵은 Claude-Opus-bluevlad에. 본 레포 `docs/`에는 **구현/운영 가이드(How)** 만.

### 주요 디렉토리

```
OpsConsole/
├── backend/          # FastAPI 서버
├── frontend/         # React + Vite
├── docs/             # 구현/운영 가이드 (How)
└── .github/          # CI 워크플로우
```

## Fix 커밋 로그 표준

- 본 프로젝트도 fix 커밋 footer 6키 (`Discovery-Method`, `Root-Cause`, `Error-Category`, `Affected-Layer`, `Recurrence`, `Prevention`) 적용 예정 (P5).
- P0~P4 단계는 일반 커밋 컨벤션(`type(scope): subject`) 사용.

## 참고 문서

- [README.md](./README.md) — 빠른 시작
- [docs/dev/quickstart.md](./docs/dev/quickstart.md) — 로컬 실행 가이드 (P0 §4 작성 예정)
- [Claude-Opus-bluevlad/services/opsconsole/](https://github.com/bluevlad/Claude-Opus-bluevlad/tree/main/services/opsconsole) — 전략·플랜·ADR 정본
- [Claude-Opus-bluevlad/standards/ops-console/](https://github.com/bluevlad/Claude-Opus-bluevlad/tree/main/standards/ops-console) — 매니페스트 스키마 정본

## 변경 이력

| 날짜 | 변경 |
|------|------|
| 2026-04-30 | 최초 작성 — P0 §0 부트스트랩 |
