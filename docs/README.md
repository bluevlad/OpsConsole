# OpsConsole 코드 저장소 문서

본 폴더는 **구현/운영 가이드(How)** 만 둡니다.

전략·플랜·ADR·로드맵 등 의사결정 문서(Why/What)는 다른 위치에 있습니다:
👉 [`Claude-Opus-bluevlad/services/opsconsole/`](https://github.com/bluevlad/Claude-Opus-bluevlad/tree/main/services/opsconsole) (private)

## 구조

| 폴더 | 내용 |
|------|------|
| `api/` | API 명세 (예정) |
| `dev/` | 로컬 개발 / 운영 / 사고 대응 / 보안 |

## 주요 문서

### 시스템 전체 파악 (먼저 읽으세요)
- **[dev/overview.md](./dev/overview.md) — 30분 가이드: 아키텍처 / DB / API / 권한 / CI / 운영**

### 빠른 시작 / 셋업
- [dev/quickstart.md](./dev/quickstart.md) — 로컬에서 OpsConsole 띄우기 (Docker compose / 호스트 직접 / 시드 / 트러블슈팅)
- [dev/database-setup.md](./dev/database-setup.md) — DB·계정·pg_hba 항목 생성
- [dev/database-init.sql](./dev/database-init.sql) — 멱등 SQL

### 통합 가이드
- [dev/github-bridge.md](./dev/github-bridge.md) — P2 GitHub Bridge (PAT/라벨/webhook 등록)
- [dev/content-integration.md](./dev/content-integration.md) — P3 본 서비스 polling client (Python 예시)
- [dev/tray-build.md](./dev/tray-build.md) — P4 Tauri 트레이 빌드·서명·배포

### 운영
- [dev/operations.md](./dev/operations.md) — 일일 운영 절차·체크리스트
- [dev/runbook.md](./dev/runbook.md) — 사고 대응 런북 (SEV-1/2/3)
- [dev/backup-restore.md](./dev/backup-restore.md) — 백업·복구 절차
- [dev/owasp-checklist.md](./dev/owasp-checklist.md) — OWASP Top 10 자가 점검 (분기 1회)
