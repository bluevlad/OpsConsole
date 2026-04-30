# OpsConsole Tray Agent (P4)

> Tauri 2.x 기반 트레이 데스크톱 앱 (Windows/macOS/Linux).
> OpsConsole 의 일부 기능 (헬스 + 변경요청 + 빠른 작업) 을 트레이로 제공.

상태: 🟡 **개발 빌드 가능, 코드 서명/배포는 인증서 발급 후**

## 빠른 시작

```bash
# (사전) Rust toolchain 설치
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"

# 의존성 + 개발 빌드
cd tray
npm install
npm run tauri:dev
```

상세: [`docs/dev/tray-build.md`](../docs/dev/tray-build.md)

## 디렉토리

```
tray/
├── package.json                 # Vite + Tauri CLI
├── vite.config.js
├── index.html
├── src/                         # React WebView UI
│   ├── App.jsx                  # 탭 라우팅
│   ├── api/tauri.js             # invoke() 래퍼
│   ├── pages/
│   │   ├── DeviceLoginPanel.jsx # 디바이스 코드 흐름 UI
│   │   ├── MySectionsPanel.jsx  # 내 섹션 + 헬스 dot
│   │   └── ChangeRequestForm.jsx# 빠른 변경요청 작성
│   └── styles.css
└── src-tauri/                   # Rust + Tauri
    ├── Cargo.toml
    ├── tauri.conf.json
    ├── capabilities/default.json
    ├── icons/                   # placeholder (출시 전 교체)
    └── src/
        ├── main.rs
        ├── lib.rs               # Tauri Builder + invoke handlers
        ├── tray.rs              # 트레이 메뉴 + 색상
        ├── api_client.rs        # OpsConsole REST + keychain
        └── notifier.rs          # OS 푸시 알림
```

## 주요 invoke 명령

| Rust 함수 | JS 호출 | 용도 |
|----------|--------|------|
| `device_init` | `cmd.deviceInit()` | device_code/user_code 발급 |
| `device_poll` | `cmd.devicePoll(deviceCode)` | 토큰 폴링 |
| `save_token` | `cmd.saveToken(token)` | OS keychain 저장 |
| `load_token` | `cmd.loadToken()` | keychain 조회 |
| `clear_token` | `cmd.clearToken()` | 로그아웃 |
| `fetch_my_sections` | `cmd.fetchMySections()` | `/api/my/sections` 프록시 |
| `open_external` | `cmd.openExternal(url)` | 기본 브라우저로 URL 열기 |

## 배포

GitHub Actions (`.github/workflows/tray-build.yml`) — `tray-v*` 태그 push 시 macOS arm64/x64 + Windows x64 빌드 + 서명 (Secrets 등록 시) + Release 자동 게시.

코드 서명 인증서 발급 절차 + GitHub Secrets 목록: [`docs/dev/tray-build.md §4·§5`](../docs/dev/tray-build.md#4-코드-서명-인증서-발급).
