//! 트레이 아이콘 + 우클릭 메뉴.

use tauri::{
    menu::{Menu, MenuItem},
    tray::{TrayIconBuilder, TrayIconEvent, MouseButton, MouseButtonState},
    AppHandle, Manager,
};

#[derive(Copy, Clone, Debug)]
pub enum Color { Ok, Warn, Err, Unknown }

pub fn install(app: &AppHandle) -> tauri::Result<()> {
    let menu = Menu::with_items(app, &[
        &MenuItem::with_id(app, "show", "OpsConsole 열기", true, None::<&str>)?,
        &MenuItem::with_id(app, "my_sections", "내 섹션 (Web)", true, None::<&str>)?,
        &MenuItem::with_id(app, "new_cr", "변경요청 작성 (Web)", true, None::<&str>)?,
        &MenuItem::with_id(app, "device_login", "디바이스 로그인", true, None::<&str>)?,
        &MenuItem::with_id(app, "logout", "로그아웃", true, None::<&str>)?,
        &MenuItem::with_id(app, "quit", "종료", true, None::<&str>)?,
    ])?;

    let _ = TrayIconBuilder::with_id("opsconsole-tray")
        .tooltip("OpsConsole")
        .icon(app.default_window_icon().expect("icon").clone())
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "show" => show_main(app),
            "my_sections" => open_url(app, "https://opsconsole.unmong.com/my/sections"),
            "new_cr" => open_url(app, "https://opsconsole.unmong.com/change-requests/new"),
            "device_login" => show_main(app), // WebView 가 device login flow 수행
            "logout" => {
                let h = app.clone();
                tauri::async_runtime::spawn(async move {
                    let _ = crate::api_client::clear_token(&h).await;
                });
            }
            "quit" => {
                app.exit(0);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            // 좌클릭 시 메인 창 토글
            if let TrayIconEvent::Click { button, button_state, .. } = event {
                if button == MouseButton::Left && button_state == MouseButtonState::Up {
                    let app = tray.app_handle();
                    show_main(app);
                }
            }
        })
        .build(app)?;

    Ok(())
}

fn show_main(app: &AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.show();
        let _ = w.set_focus();
    }
}

fn open_url(app: &AppHandle, url: &str) {
    use tauri_plugin_shell::ShellExt;
    let _ = app.shell().open(url.to_string(), None);
}

/// 헬스 색상 반영 — Tauri 2.x 에서는 tooltip 만 갱신 (아이콘 PNG 교체는 추후).
pub fn set_color(app: &AppHandle, color: Color) {
    let label = match color {
        Color::Ok => "OpsConsole · 모든 섹션 정상",
        Color::Warn => "OpsConsole · 일부 섹션 응답 없음",
        Color::Err => "OpsConsole · 헬스 실패 섹션 발생",
        Color::Unknown => "OpsConsole",
    };
    if let Some(tray) = app.tray_by_id("opsconsole-tray") {
        let _ = tray.set_tooltip(Some(label));
    }
}
