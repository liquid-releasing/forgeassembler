// Turn an absolute filesystem path into a URL a <video>/<img> can load.
//
// Chromium blocks file:/// for media inside the webview; Tauri's asset
// protocol (convertFileSrc, enabled in tauri.conf.json) proxies the read.
// Falls back to a file:// URL in browser-mock mode.
import { convertFileSrc } from '@tauri-apps/api/core';

export function toMediaUrl(path) {
  if (!path) return undefined;
  try {
    return convertFileSrc(path);
  } catch {
    const fwd = String(path).replace(/\\/g, '/');
    return fwd.startsWith('/') ? `file://${fwd}` : `file:///${fwd}`;
  }
}
