import { describe, it, expect } from 'vitest';
import {
  PROJECT_EXT, PROJECT_FILTERS, LEGACY_PROJECT_SUFFIX,
  projectFileName, isProjectPath, projectDisplayName,
} from './projectFile.js';

describe('projectFileName', () => {
  it('names a new project with the new extension', () => {
    expect(projectFileName('vol_03')).toBe('vol_03.forgeproject');
  });

  it('does not stack extensions on a name that already has one', () => {
    expect(projectFileName('vol_03.forgeproject')).toBe('vol_03.forgeproject');
    expect(projectFileName('vol_03.forgeproject.json')).toBe('vol_03.forgeproject');
  });

  it('replaces characters Windows will not take', () => {
    // Replaced, not stripped: "a:b" and "ab" must not become one file.
    expect(projectFileName('Katie: part 2')).toBe('Katie- part 2.forgeproject');
    expect(projectFileName('a/b\\c')).toBe('a-b-c.forgeproject');
  });

  it('always produces something openable', () => {
    expect(projectFileName('')).toBe('untitled.forgeproject');
    expect(projectFileName(null)).toBe('untitled.forgeproject');
    expect(projectFileName(42)).toBe('untitled.forgeproject');
  });

  it('keeps a name made entirely of illegal characters rather than blanking it', () => {
    // "---" is a legal filename and it is what the user typed. Falling
    // back to "untitled" here would quietly rename their project.
    expect(projectFileName('///')).toBe('---.forgeproject');
  });
});

describe('isProjectPath', () => {
  it('accepts both names, so old projects still open', () => {
    expect(isProjectPath('D:\\work\\vol_03.forgeproject')).toBe(true);
    expect(isProjectPath('D:\\work\\vol_03.forgeproject.json')).toBe(true);
  });

  it('ignores case, because Windows does', () => {
    expect(isProjectPath('D:\\work\\VOL_03.ForgeProject')).toBe(true);
  });

  it('rejects the sidecars that sit beside one', () => {
    // The reason the extension changed: a folder of these used to be
    // listed alongside the project in the open dialog.
    expect(isProjectPath('D:\\out\\scene.chapters.json')).toBe(false);
    expect(isProjectPath('D:\\out\\scene.funscript')).toBe(false);
    expect(isProjectPath('D:\\out\\scene.forge')).toBe(false);
    expect(isProjectPath('')).toBe(false);
    expect(isProjectPath(null)).toBe(false);
  });
});

describe('projectDisplayName', () => {
  it('strips the path and either extension', () => {
    expect(projectDisplayName('D:\\work\\vol_03.forgeproject')).toBe('vol_03');
    expect(projectDisplayName('/mnt/work/vol_03.forgeproject.json')).toBe('vol_03');
  });

  it('takes the LEGACY suffix off whole', () => {
    // Testing the new extension first would leave ".forgeproject"
    // dangling on every older project's title bar.
    expect(projectDisplayName('vol_03.forgeproject.json'))
      .not.toContain(PROJECT_EXT);
  });

  it('leaves a name that is not a project file alone', () => {
    expect(projectDisplayName('notes.txt')).toBe('notes.txt');
    expect(projectDisplayName('')).toBe('');
  });
});

describe('the open dialog filters', () => {
  it('offers the new extension first, so it is the default', () => {
    expect(PROJECT_FILTERS[0].extensions).toEqual([PROJECT_EXT]);
  });

  it('keeps a way to reach an older project', () => {
    // Windows matches the LAST extension only, so a .forgeproject.json
    // can only be caught by a `json` filter -- which is why it is a
    // separate entry rather than merged into the first.
    expect(PROJECT_FILTERS.some(f => f.extensions.includes('json'))).toBe(true);
    expect(LEGACY_PROJECT_SUFFIX.endsWith('.json')).toBe(true);
  });
});
