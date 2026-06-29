// mediaUrl.test.js — covers the browser-mock fallback path of toMediaUrl.
//
// In the vitest (non-Tauri) environment, @tauri-apps/api/core's
// convertFileSrc throws (no window.__TAURI_INTERNALS__), so toMediaUrl
// falls back to a file:// URL. That fallback is pure and testable; the
// Tauri asset-protocol branch needs the runtime and is intentionally
// not exercised here.
import { describe, it, expect } from 'vitest';
import { toMediaUrl } from './mediaUrl.js';

describe('toMediaUrl', () => {
  it('returns undefined for empty / nullish input', () => {
    expect(toMediaUrl('')).toBeUndefined();
    expect(toMediaUrl(null)).toBeUndefined();
    expect(toMediaUrl(undefined)).toBeUndefined();
  });

  it('normalizes Windows backslashes and prefixes file:///', () => {
    expect(toMediaUrl('C:\\Users\\bruce\\clip.mp4'))
      .toBe('file:///C:/Users/bruce/clip.mp4');
  });

  it('keeps forward-slash absolute Windows paths', () => {
    expect(toMediaUrl('C:/a/b.mp4')).toBe('file:///C:/a/b.mp4');
  });

  it('uses two slashes for POSIX-rooted paths', () => {
    expect(toMediaUrl('/home/u/clip.mp4')).toBe('file:///home/u/clip.mp4');
  });
});
