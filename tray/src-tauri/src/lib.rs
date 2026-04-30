//! OpsConsole tray agent — Tauri 2.x main library.
//!
//! 컨셉:
//! - 트레이 아이콘 + 우클릭 메뉴 (Show / Quit / 헬스 색상 dot)
//! - 메인 창은 기본 숨김. 트레이 클릭 또는 메뉴에서 열림
//! - WebView (React) 가 OpsConsole API 호출 — 토큰은 OS keychain
//! - 5분 주기 헬스 polling → 트레이 색상 갱신 + 실패 시 OS 푸시 알림

mod api_client;
mod notifier;
mod tray;

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager};

/// 트레이 앱이 WebView 에 노출하는 명령. invoke('cmd_name', args) 로 호출.
#[derive(Serialize, Deserialize, Debug)]
pub struct DeviceInitOut {
    pub device_code: String,
    pub user_code: String,
    pub verification_uri: String,
    pub expires_in: u32,
    pub interval: u32,
}

#[tauri::command]
async fn device_init() -> Result<DeviceInitOut, String> {
    api_client::device_init().await.map_err(|e| e.to_string())
}

#[tauri::command]
async fn device_poll(device_code: String) -> Result<serde_json::Value, String> {
    api_client::device_poll(&device_code)
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
async fn save_token(app: AppHandle, token: String) -> Result<(), String> {
    api_client::save_token(&app, &token)
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
async fn load_token(app: AppHandle) -> Result<Option<String>, String> {
    api_client::load_token(&app)
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
async fn clear_token(app: AppHandle) -> Result<(), String> {
    api_client::clear_token(&app)
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
async fn fetch_my_sections(app: AppHandle) -> Result<serde_json::Value, String> {
    let token = api_client::load_token(&app)
        .await
        .map_err(|e| e.to_string())?
        .ok_or_else(|| "no token".to_string())?;
    api_client::get_json(&token, "/api/my/sections")
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
async fn open_external(app: AppHandle, url: String) -> Result<(), String> {
    use tauri_plugin_shell::ShellExt;
    app.shell()
        .open(url, None)
        .map_err(|e| e.to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info")).init();

    tauri::Builder::default()
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_store::Builder::default().build())
        .invoke_handler(tauri::generate_handler![
            device_init,
            device_poll,
            save_token,
            load_token,
            clear_token,
            fetch_my_sections,
            open_external,
        ])
        .setup(|app| {
            // 트레이 아이콘 부팅
            tray::install(app.handle())?;

            // 5분 주기 헬스 폴링
            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                loop {
                    if let Err(e) = poll_once(&app_handle).await {
                        log::warn!("health poll error: {e}");
                    }
                    tokio::time::sleep(std::time::Duration::from_secs(300)).await;
                }
            });

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

async fn poll_once(app: &AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let token = match api_client::load_token(app).await? {
        Some(t) => t,
        None => return Ok(()), // 미로그인 — 폴링 생략
    };
    let json: serde_json::Value =
        api_client::get_json(&token, "/api/my/sections").await?;
    let sections = json.as_array().ok_or("bad shape")?;
    let mut warn_count = 0;
    let mut err_count = 0;
    for s in sections {
        let h = s.get("health").and_then(|v| v.as_object());
        if let Some(h) = h {
            let last_ok = h.get("last_ok").and_then(|v| v.as_bool());
            match last_ok {
                Some(false) => err_count += 1,
                None => warn_count += 1,
                _ => {}
            }
        }
    }

    let total = sections.len();
    let color = if err_count > 0 {
        tray::Color::Err
    } else if warn_count > 0 {
        tray::Color::Warn
    } else {
        tray::Color::Ok
    };
    tray::set_color(app, color);

    if err_count > 0 {
        let _ = notifier::notify(app, "OpsConsole — 헬스 경고",
            &format!("{}건 섹션이 비정상 ({}개 중)", err_count, total));
    }
    Ok(())
}
