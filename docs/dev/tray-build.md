# Tauri 트레이 앱 빌드·서명 가이드 (P4)

> OpsConsole 트레이 데스크톱 앱(Windows MSI / macOS DMG) 의 개발·빌드·서명·배포.

---

## 0. 개요

| 항목 | 값 |
|------|------|
| 프레임워크 | Tauri 2.x (Rust + WebView) |
| Frontend | React 18 + Vite |
| Backend (Rust) | reqwest, keyring, tauri-plugin-{notification, shell, store} |
| 디바이스 인증 | OAuth 2.0 디바이스 코드 흐름 (RFC 8628 단순화) |
| 토큰 저장 | OS Keychain (macOS Keychain / Windows Credential Manager / Linux Secret Service) |
| 자동 업데이트 | Tauri updater (서명 키 발급 후 활성화) |

---

## 1. 사전 조건 (개발 머신)

### 1.1 Rust toolchain

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
# 또는 brew install rustup-init && rustup-init
source "$HOME/.cargo/env"
rustc --version  # 1.77 이상
```

### 1.2 Tauri CLI

```bash
cargo install tauri-cli --version "^2.1" --locked
```

### 1.3 macOS 추가 의존성

```bash
xcode-select --install
```

### 1.4 Windows 추가 의존성

- Visual Studio 2022 Build Tools (C++ workload)
- WebView2 Runtime (Win10 1809+ 기본 포함, Win10 이전은 https://developer.microsoft.com/microsoft-edge/webview2/)

### 1.5 아이콘 생성 (1회)

`tray/src-tauri/icons/` 에 1024x1024 원본 1장 두고:

```bash
cd tray
npx @tauri-apps/cli icon src-tauri/icons/icon.png -o src-tauri/icons
# → icon.icns, icon.ico, 32x32.png, 128x128.png, 128x128@2x.png 자동 생성
```

> 본 레포에는 단색 placeholder PNG 만 포함됨. 실제 출시 전 디자인 아이콘으로 교체.

---

## 2. 개발 빌드 (로컬 dev)

```bash
cd tray
npm install
npm run tauri:dev
```

이때 자동 수행:
1. `vite dev` 가 4101 포트에서 React UI 서빙
2. Cargo 가 Rust 코드 + Tauri 컴파일 (첫 빌드는 5~15분, 캐시 후 1~2분)
3. WebView 윈도우 열림 + 트레이 아이콘 표시
4. 백엔드 OpsConsole API (`https://opsconsole.unmong.com`) 와 통신

`OPSCONSOLE_BASE_URL=http://localhost:9100 cargo run` 으로 로컬 백엔드 사용 가능.

### 디바이스 로그인 흐름 검증

1. 트레이 앱 실행 → 메인 창 → "로그인 시작"
2. 8자 user_code 표시 + 브라우저 자동 오픈 → `https://opsconsole.unmong.com/device?code=XXXX-XXXX`
3. 브라우저에서 Google 로그인된 상태로 "이 디바이스를 내 계정으로 승인" 클릭
4. 트레이 앱이 5초 polling 후 token 획득 → keychain 저장
5. 트레이 앱 재시작해도 자동 로그인 유지

---

## 3. 프로덕션 빌드 (서명 없이 — 내부 검증용)

```bash
cd tray
npm run tauri:build
# 산출물:
#   src-tauri/target/release/bundle/dmg/OpsConsole_0.0.1_aarch64.dmg     (macOS)
#   src-tauri/target/release/bundle/msi/OpsConsole_0.0.1_x64_en-US.msi    (Windows)
```

> ⚠️ 서명 없는 macOS dmg 는 Gatekeeper 가 차단. 우클릭 → 열기 또는 `xattr -d com.apple.quarantine` 로 우회 가능.
> ⚠️ 서명 없는 Windows MSI 는 SmartScreen 경고. 정식 배포 전에는 EV 코드 서명 필수.

---

## 4. 코드 서명 인증서 발급

### 4.1 Apple Developer Program

- 가입: https://developer.apple.com/programs/ ($99/yr)
- Xcode 또는 Apple Developer 웹에서 "Developer ID Application" 인증서 생성
- macOS Keychain 으로 export → `.p12` 파일 + 비밀번호

### 4.2 Windows Code Signing

| 종류 | 비용 | SmartScreen | 발급기간 |
|------|------|-------------|----------|
| Standard Code Signing | ~$80~150/yr | 초기 reputation 빌드 후 통과 | 1~3일 |
| EV Code Signing | ~$300~500/yr | 즉시 통과 | 2~5일 (HSM/USB 토큰) |

권장 발급처: SSL.com, DigiCert, Sectigo

### 4.3 Tauri Updater 키 (자체 서명)

```bash
cargo install tauri-cli --locked
tauri signer generate -w ~/.tauri/opsconsole-tray.key
# → 공개키는 src-tauri/tauri.conf.json 의 `updater.pubkey` 에 붙여넣기
# → 비밀키는 GitHub Secrets 에만, 절대 레포 커밋 금지
```

---

## 5. GitHub Secrets 등록

레포 → Settings → Secrets and variables → Actions:

| Secret | 용도 |
|--------|------|
| `APPLE_CERT_BASE64` | `.p12` 파일을 `base64 -i cert.p12` 로 인코딩한 문자열 |
| `APPLE_CERT_PASSWORD` | `.p12` export 시 설정한 비밀번호 |
| `APPLE_SIGNING_IDENTITY` | 예: `Developer ID Application: bluevlad (TEAMID)` |
| `APPLE_ID` | Apple ID 이메일 |
| `APPLE_PASSWORD` | App-specific password (https://appleid.apple.com/account/manage) |
| `APPLE_TEAM_ID` | Developer Portal → Membership |
| `TAURI_SIGNING_PRIVATE_KEY` | `tauri signer generate` 의 비밀키 내용 |
| `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` | 비밀키 비밀번호 |

Windows EV 토큰은 GitHub Actions 표준 워크플로로는 어려움 (USB 토큰). 자체 self-hosted runner 또는 별도 클라우드 서명 서비스 사용.

---

## 6. CI 빌드 (GitHub Actions)

`.github/workflows/tray-build.yml` 워크플로:

- 트리거: `tray-v*` 태그 push 또는 manual workflow_dispatch
- 매트릭스: macOS arm64 + macOS x64 + Windows x64
- 산출물: 각 OS 별 .dmg / .msi
- 태그 빌드 시 GitHub Release 자동 생성

릴리스 절차:
```bash
git tag tray-v0.0.1
git push origin tray-v0.0.1
# → GitHub Actions 가 빌드·서명 후 Release 자동 게시
```

---

## 7. 자동 업데이트 (활성화 절차)

1. `tauri.conf.json` 의 `plugins.updater.active` 를 `true` 로
2. `pubkey` 자리에 §4.3 의 공개키 붙여넣기
3. 릴리스 시 `*.app.tar.gz` (mac) 또는 `*.msi.zip` (win) 옆에 `latest.json` 매니페스트 자동 생성
4. `latest.json` 을 `https://opsconsole.unmong.com/updates/{platform}/{arch}/{version}` 에 호스팅
   - 정적 파일 호스팅: GitHub Pages, Cloudflare R2 등
   - OpsConsole 게이트웨이에 직접 nginx location 추가도 가능

---

## 8. 트러블슈팅

| 증상 | 원인 / 조치 |
|------|------------|
| `error: failed to run custom build command for 'tauri-plugin-tray'` | macOS framework 누락. `xcode-select --install` 후 재시도 |
| Linux: `error: failed to find development files for at-spi2-atk` | `sudo apt install libgtk-3-dev libwebkit2gtk-4.1-dev libayatana-appindicator3-dev librsvg2-dev` |
| Windows: `MSI tool not found` | Wix Toolset 자동 다운로드 — 인터넷 차단 환경에서는 미리 설치 |
| 트레이 아이콘 안 보임 | 1) `default_window_icon` 미설정 — `tauri.conf.json` icons 배열 확인 2) macOS 다크 모드 — placeholder 단색은 안 보일 수 있음, 실제 디자인 아이콘 필요 |
| 디바이스 로그인 후 toklen 분실 | `keyring::Error::NoEntry` — 다른 사용자 계정으로 로그인된 상태인지 확인. macOS 의 경우 Keychain Access 에서 'opsconsole-tray' 검색 |
| `403 csp violation` from WebView | `tauri.conf.json` 의 `app.security.csp` 에서 `connect-src` 에 OpsConsole 도메인 포함 확인 |

---

## 9. 보안 노트

- **Keychain entry**: service="opsconsole-tray" account="default-token". 운영자가 본인 계정으로 macOS Keychain Access 에서 직접 폐기 가능
- **자동 업데이트 키 분실 시 재서명 불가** — 백업 정책 필수 (1Password / 회사 vault)
- **WebView CSP**: `connect-src` 가 OpsConsole 도메인으로 한정. 임의 도메인 호출 차단
- **device_code 노출 금지**: 트레이 → 백엔드 통신에서만 사용. 로그·UI 표시 금지 (user_code 만 노출)
- **로그아웃**: `keychain entry delete` + 백엔드 측 토큰 폐기는 P5 (refresh_token + revoke endpoint) 에서 본격 처리
