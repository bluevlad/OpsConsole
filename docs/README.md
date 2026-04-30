# OpsConsole 코드 저장소 문서

본 폴더는 **구현/운영 가이드(How)** 만 둡니다.

전략·플랜·ADR·로드맵 등 의사결정 문서(Why/What)는 다른 위치에 있습니다:
👉 [`Claude-Opus-bluevlad/services/opsconsole/`](https://github.com/bluevlad/Claude-Opus-bluevlad/tree/main/services/opsconsole) (private)

## 구조

| 폴더 | 내용 |
|------|------|
| `api/` | API 명세 (라우터별 요청/응답 예제) |
| `dev/` | 로컬 개발/실행 가이드, 디버깅 팁 |

## 주요 문서

- [dev/quickstart.md](./dev/quickstart.md) — 로컬에서 OpsConsole 띄우기 (P0 §4)
- (예정) `api/manifest-sync.md` — POST /api/catalog/sync 사용법
- (예정) `dev/database-setup.md` — 공유 PostgreSQL에 `opsconsole_dev` DB 만드는 법
