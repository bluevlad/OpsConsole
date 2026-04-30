# OpsConsole

운영자/섹션 담당자가 코드 변경 없이 멀티 서비스의 섹션 메타데이터·콘텐츠·헬스·변경요청을 관리하는 **Internal Developer Portal (IDP)**.

> 🟡 **상태**: P0 부트스트랩 진행 중 (코드 저장소 신규 등록).
> 1호 고객: AllergyInsight (`allergy.unmong.com`).
> 전략·플랜·ADR 정본은 [`Claude-Opus-bluevlad/services/opsconsole/`](https://github.com/bluevlad/Claude-Opus-bluevlad/tree/main/services/opsconsole) (private repo).

---

## 한 줄 요약

> "Claude/IDE를 띄우기 어려운 환경에서도, 섹션 담당자가 웹 또는 트레이 앱으로 자기 섹션의 상태를 모니터링하고 콘텐츠를 편집하며 변경요청을 GitHub Issue/PR로 제출할 수 있도록 한다."

## 컨테이너 구성

| 컨테이너 | 포트 | 역할 |
|----------|------|------|
| opsconsole-frontend | 4100 | React 18 + Vite 운영자 UI |
| opsconsole-backend  | 9100 | FastAPI 카탈로그/콘텐츠/브리지 API |
| opsconsole-tray (P4) | — | Tauri Windows/Mac 트레이 Agent |

PostgreSQL은 **공유 컨테이너**(`172.30.1.72:5432`)를 사용합니다. DB명: `opsconsole`(prod) / `opsconsole_dev`(dev), 테이블 prefix: `ops_`.

## 빠른 시작 (로컬 개발)

```bash
# 0) 환경변수 준비
cp .env.example .env
# .env 안의 CHANGE_ME 값을 채운다 (DATABASE_URL, JWT_SECRET_KEY 등)

# 1) Docker 통합 기동 (백엔드 + 프런트, hot reload)
docker compose -f docker-compose.dev.yml up --build

# 2) 헬스 확인
curl http://localhost:9100/api/health    # → {"status": "ok"}
open  http://localhost:4100              # → React 앱
```

상세 가이드: [`docs/dev/quickstart.md`](./docs/dev/quickstart.md)

## 디렉토리 구조

```
OpsConsole/
├── backend/                      # FastAPI 서버
│   ├── app/
│   │   ├── api/                  # 라우터 (health, auth, services, sections, sync, ...)
│   │   ├── core/                 # 설정, 보안, 의존성
│   │   ├── database/             # async engine + alembic 마이그레이션
│   │   ├── manifest/             # 매니페스트 스키마/parser/fetcher/sync
│   │   ├── models/               # SQLAlchemy ORM
│   │   └── main.py
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                     # React 18 + Vite
│   ├── src/
│   │   ├── pages/                # LoginPage, ServicesListPage, SectionsListPage, SectionDetailPage
│   │   ├── components/           # SectionCard, AssetList, SyncButton
│   │   ├── api/                  # axios + JWT interceptor
│   │   └── App.jsx
│   ├── package.json
│   └── Dockerfile
├── docs/                         # 코드 저장소 구현/운영 가이드 (How)
│   ├── api/                      # API 명세
│   └── dev/                      # 개발/실행 가이드
├── docker-compose.yml            # prod
├── docker-compose.dev.yml        # dev (hot reload)
├── .env.example
├── README.md                     # 본 문서
└── CLAUDE.md                     # Claude Code 진입점
```

## 매니페스트 기반 카탈로그

각 서비스 코드 저장소에 `ops/manifest.yml` 파일 1개만 두면 OpsConsole이 카탈로그를 자동 구성합니다.

- 스키마 정본: [`standards/ops-console/manifest-schema.yml`](https://github.com/bluevlad/Claude-Opus-bluevlad/blob/main/standards/ops-console/manifest-schema.yml)
- 1호 고객 시드: AllergyInsight 11섹션 — Claude-Opus-bluevlad 내 `services/allergyinsight/dev/ops-manifest-seed.yml`

## 로드맵

| Phase | 내용 | 상태 |
|-------|------|------|
| **P0** | 카탈로그 + 자동 스캔 + 웹 읽기전용 대시보드 | 🟡 진행 중 |
| **P1** | 담당자 지정 + 헬스 모니터링 + 알림 | 📋 계획 |
| **P2** | GitHub Bridge (Issue/PR 자동) | 📋 계획 |
| **P3** | 콘텐츠 블록 에디터 | 📋 계획 |
| **P4** | Tauri 트레이 Agent | 📋 계획 |
| **P5** | 권한·감사·배포 | 📋 계획 |

전체 일정·플랜·ADR: [`Claude-Opus-bluevlad/services/opsconsole/`](https://github.com/bluevlad/Claude-Opus-bluevlad/tree/main/services/opsconsole)

## 라이선스

Internal — bluevlad

## 변경 이력

| 날짜 | 변경 |
|------|------|
| 2026-04-30 | 최초 등록 — P0 §0 부트스트랩 |
