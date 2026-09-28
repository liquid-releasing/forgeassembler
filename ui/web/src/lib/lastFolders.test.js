import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import {
  baseName, parentFolder, lastFolder, rememberFolder, rememberFileFolder, forgetFolders,
} from './lastFolders.js';

describe('parentFolder', () => {
  it('takes the folder off a Windows path', () => {
    expect(parentFolder('D:\\videos\\set\\scene.forge')).toBe('D:\\videos\\set');
  });

  it('takes the folder off a POSIX path', () => {
    // A project file can carry either separator depending on where it
    // was written.
    expect(parentFolder('/mnt/media/set/scene.forge')).toBe('/mnt/media/set');
  });

  it('ignores a trailing separator', () => {
    expect(parentFolder('D:\\videos\\set\\')).toBe('D:\\videos');
  });

  it('keeps a drive root as a root', () => {
    // "C:" on its own is not a folder anything can open.
    expect(parentFolder('C:\\scene.forge')).toBe('C:\\');
  });

  it('has no answer for something with no parent', () => {
    expect(parentFolder('scene.forge')).toBeNull();
    expect(parentFolder('')).toBeNull();
    expect(parentFolder(null)).toBeNull();
    expect(parentFolder(42)).toBeNull();
  });
});

describe('without localStorage', () => {
  // This is the test runner's own situation, and a private window's. The
  // whole point is that a file dialog still opens.
  it('reads as empty and writing is a no-op, never a throw', () => {
    expect(typeof globalThis.localStorage).toBe('undefined');
    expect(lastFolder('scenes')).toBeNull();
    expect(() => rememberFolder('scenes', 'D:\\videos')).not.toThrow();
    expect(() => rememberFileFolder('scenes', 'D:\\videos\\a.forge')).not.toThrow();
    expect(() => forgetFolders()).not.toThrow();
    expect(lastFolder('scenes')).toBeNull();
  });
});

describe('with localStorage', () => {
  let store;
  beforeEach(() => {
    store = new Map();
    globalThis.localStorage = {
      getItem: (k) => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => store.set(k, String(v)),
      removeItem: (k) => store.delete(k),
    };
  });
  afterEach(() => { delete globalThis.localStorage; });

  it('remembers a folder per kind, independently', () => {
    rememberFolder('scenes', 'E:\\videos\\set');
    rememberFolder('output', 'D:\\forged');
    expect(lastFolder('scenes')).toBe('E:\\videos\\set');
    expect(lastFolder('output')).toBe('D:\\forged');
  });

  it('remembers the folder a file came from', () => {
    rememberFileFolder('project', 'D:\\work\\comp.forgeproject.json');
    expect(lastFolder('project')).toBe('D:\\work');
  });

  it('keeps the other kinds when one changes', () => {
    rememberFolder('scenes', 'E:\\a');
    rememberFolder('output', 'D:\\b');
    rememberFolder('scenes', 'E:\\c');
    expect(lastFolder('scenes')).toBe('E:\\c');
    expect(lastFolder('output')).toBe('D:\\b');
  });

  it('ignores a value with nothing in it', () => {
    rememberFolder('scenes', 'E:\\a');
    rememberFolder('scenes', '');
    rememberFolder('scenes', null);
    rememberFileFolder('scenes', 'no-parent.forge');
    expect(lastFolder('scenes')).toBe('E:\\a');
  });

  it('survives corrupt stored data rather than throwing', () => {
    store.set('fa.lastFolders', '{not json');
    expect(lastFolder('scenes')).toBeNull();
    rememberFolder('scenes', 'E:\\a');
    expect(lastFolder('scenes')).toBe('E:\\a');
  });

  it('survives stored data of the wrong shape', () => {
    store.set('fa.lastFolders', '"a string"');
    expect(lastFolder('scenes')).toBeNull();
  });

  it('survives a storage that refuses to write', () => {
    globalThis.localStorage.setItem = () => { throw new Error('quota'); };
    expect(() => rememberFolder('scenes', 'E:\\a')).not.toThrow();
  });

  it('forgets on request', () => {
    rememberFolder('scenes', 'E:\\a');
    forgetFolders();
    expect(lastFolder('scenes')).toBeNull();
  });
});

describe('baseName', () => {
  it('takes the name off a Windows path', () => {
    // The bug it replaces: a regex class that matched only the forward
    // slash, so this whole string came back and the footer read
    // "Saved D:\\\\__lqr_releases\\\\...".
    expect(baseName("D:\\__lqr_releases\\-Madmartigan- - It's Just AI Sex\\its-just-ai-sex.forgeproject")).toBe('its-just-ai-sex.forgeproject');
  });

  it('takes the name off a POSIX path', () => {
    expect(baseName('/d/rel/name.forgeproject')).toBe('name.forgeproject');
  });

  it('ignores a trailing separator', () => {
    expect(baseName('D:\\rel\\folder\\')).toBe('folder');
  });

  it('passes through a bare name', () => {
    expect(baseName('name.forgeproject')).toBe('name.forgeproject');
  });

  it('survives nothing', () => {
    expect(baseName('')).toBe('');
    expect(baseName(null)).toBe('');
  });
});
