//! OpsConsole REST 클라이언트 + OS keychain 토큰 저장.
//!
//! Keychain entry: service="opsconsole-tray" account="default-token".
//! Tauri 의 keyring 크레이트가 macOS Keychain / Windows Credential Manager / Linux Secret Service 통합.

use crate::DeviceInitOut;
use anyhow::Result;
use keyring::Entry;
use reqwest::Client;
use serde_json::Value;
use tauri::AppHandle;

const SERVICE: &str = "opsconsole-tray";
const ACCOUNT: &str = "default-token";

fn base_url() -> String {
    std::env::var("OPSCONSOLE_BASE_URL")
        .unwrap_or_else(|_| "https://opsconsole.unmong.com".to_string())
}

fn keyring_entry() -> keyring::Result<Entry> {
    Entry::new(SERVICE, ACCOUNT)
}

pub async fn save_token(_app: &AppHandle, token: &str) -> Result<()> {
    let entry = keyring_entry()?;
    entry.set_password(token)?;
    Ok(())
}

pub async fn load_token(_app: &AppHandle) -> Result<Option<String>> {
    match keyring_entry() {
        Ok(entry) => match entry.get_password() {
            Ok(s) => Ok(Some(s)),
            Err(keyring::Error::NoEntry) => Ok(None),
            Err(e) => Err(e.into()),
        },
        Err(e) => Err(e.into()),
    }
}

pub async fn clear_token(_app: &AppHandle) -> Result<()> {
    if let Ok(entry) = keyring_entry() {
        if let Err(e) = entry.delete_credential() {
            // NoEntry 는 무시
            if !matches!(e, keyring::Error::NoEntry) {
                return Err(e.into());
            }
        }
    }
    Ok(())
}

fn build_client() -> Result<Client> {
    let c = Client::builder()
        .user_agent("OpsConsole-Tray/0.0.1")
        .timeout(std::time::Duration::from_secs(10))
        .build()?;
    Ok(c)
}

pub async fn get_json(token: &str, path: &str) -> Result<Value> {
    let url = format!("{}{}", base_url(), path);
    let res = build_client()?
        .get(&url)
        .bearer_auth(token)
        .send()
        .await?;
    if !res.status().is_success() {
        anyhow::bail!("{} {}: {}", res.status(), &url, res.text().await.unwrap_or_default());
    }
    Ok(res.json().await?)
}

pub async fn device_init() -> Result<DeviceInitOut> {
    let url = format!("{}/api/auth/device/init", base_url());
    let payload = serde_json::json!({
        "device_label": format!("{} ({})", whoami_label(), std::env::consts::OS),
        "user_agent": "OpsConsole-Tray/0.0.1",
    });
    let res = build_client()?.post(&url).json(&payload).send().await?;
    if !res.status().is_success() {
        anyhow::bail!("{} init: {}", res.status(), res.text().await.unwrap_or_default());
    }
    Ok(res.json().await?)
}

pub async fn device_poll(device_code: &str) -> Result<Value> {
    let url = format!("{}/api/auth/device/poll", base_url());
    let payload = serde_json::json!({ "device_code": device_code });
    let res = build_client()?.post(&url).json(&payload).send().await?;
    let status = res.status();
    let body: Value = res.json().await.unwrap_or(Value::Null);
    if !status.is_success() && status.as_u16() != 410 {
        anyhow::bail!("{}: {:?}", status, body);
    }
    Ok(body)
}

fn whoami_label() -> String {
    std::env::var("USER")
        .or_else(|_| std::env::var("USERNAME"))
        .unwrap_or_else(|_| "user".to_string())
}
