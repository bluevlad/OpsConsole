// Rust 측 invoke 래퍼.
import { invoke } from '@tauri-apps/api/core';

export const cmd = {
  deviceInit: () => invoke('device_init'),
  devicePoll: (deviceCode) => invoke('device_poll', { deviceCode }),
  saveToken: (token) => invoke('save_token', { token }),
  loadToken: () => invoke('load_token'),
  clearToken: () => invoke('clear_token'),
  fetchMySections: () => invoke('fetch_my_sections'),
  openExternal: (url) => invoke('open_external', { url }),
};
