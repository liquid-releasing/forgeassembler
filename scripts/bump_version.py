#!/usr/bin/env python3
"""Set the app version everywhere it is written down.

The version lives in four files that must agree, and one that must
deliberately disagree:

  ui/web/package.json              full label ("0.1.1-alpha"). What the UI
                                   reads, so it is what the window and About
                                   panel show.
  ui/web/src-tauri/Cargo.toml      full label. The Rust crate version.
  ui/web/src-tauri/Cargo.lock      the crate's own entry. Left behind, cargo
                                   silently rewrites it mid-build, which shows
                                   up as a dirty tree in CI and a diff nobody
                                   authored.
  ui/web/src-tauri/tauri.conf.json STRIPPED ("0.1.1"). The MSI bundler refuses
                                   a non-numeric pre-release identifier, so the
                                   marketing suffix cannot go here. A hard
                                   Tauri constraint, not a style choice.

The WEBSITE is not in that list, unlike FunscriptForge's. forgeassembler-web
reads its badge from `latest-version.json`, which its own `sync-version.yml`
rewrites when the release workflow dispatches `release-published`. Nothing to
bump by hand, so nothing here pretends to.

Usage:
    python scripts/bump_version.py 0.1.1-alpha
    python scripts/bump_version.py --check            # verify agreement
    python scripts/bump_version.py --dev-stamp abc1234

Files are rewritten byte-for-byte apart from the version itself: line endings
are preserved and JSON is patched textually rather than re-serialised, so
formatting and key order survive.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# A label like 0.1.1-alpha. The suffix is optional and free-form; only
# tauri.conf.json cares, and it gets stripped there.
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?$")


def strip_suffix(version: str) -> str:
    """Drop a pre-release label: 0.1.1-alpha -> 0.1.1 (MSI constraint)."""
    return version.split("-", 1)[0]


def _read(path: Path) -> str:
    # newline="" keeps CRLF intact so a bump is not a whole-file diff.
    return path.read_text(encoding="utf-8", newline="")


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="")


def _sub_once(text: str, pattern: re.Pattern[str], new: str, what: str) -> str:
    """Replace exactly one match, or fail loudly.

    A silent no-op is the whole failure mode this script exists to prevent, so
    an anchor that stops matching is an error rather than a version that
    quietly stays behind.
    """
    text, n = pattern.subn(new, text, count=1)
    if n != 1:
        raise SystemExit(f"bump_version: anchor did not match in {what}")
    return text


def _targets(version: str):
    """(path, anchor with the version as group 2, replacement, value)."""
    return [
        (
            REPO / "ui/web/package.json",
            re.compile(r'("version"\s*:\s*")([^"]+)(")'),
            version,
        ),
        (
            REPO / "ui/web/src-tauri/Cargo.toml",
            re.compile(r'(?m)^(version\s*=\s*")([^"]+)(")'),
            version,
        ),
        (
            # Anchored on the package NAME, so a dependency that happens to
            # sit at the same version is never touched.
            REPO / "ui/web/src-tauri/Cargo.lock",
            re.compile(r'(?s)(name = "forgeassembler".{1,2}version = ")([^"]+)(")'),
            version,
        ),
        (
            REPO / "ui/web/src-tauri/tauri.conf.json",
            re.compile(r'("version"\s*:\s*")([^"]+)(")'),
            strip_suffix(version),
        ),
    ]


def apply(version: str) -> int:
    changed = 0
    for path, anchor, value in _targets(version):
        if not path.exists():
            print(f"  SKIP  {path} (not found)")
            continue
        before = _read(path)
        after = _sub_once(before, anchor, rf"\g<1>{value}\g<3>", str(path))
        if before == after:
            print(f"  ok    {path.name} already {value}")
            continue
        _write(path, after)
        print(f"  BUMP  {path.name} -> {value}")
        changed += 1
    return changed


def dev_stamp(sha: str) -> int:
    """Mark a build-only dispatch so it cannot be mistaken for a release.

    Only package.json is touched, because that is the file the UI reads.
    tauri.conf.json is deliberately left alone: the MSI bundler rejects a
    non-numeric pre-release identifier, and build metadata is no safer.

    FunscriptForge lost half a session on 2026-09-05 to a dispatch build and a
    release being indistinguishable in the UI, debugging a feature that was
    simply not in the installed binary.
    """
    path = REPO / "ui/web/package.json"
    anchor = re.compile(r'("version"\s*:\s*")([^"]+)(")')
    before = _read(path)
    m = anchor.search(before)
    if not m:
        raise SystemExit("bump_version: no version in package.json")
    base = m.group(2).split("+", 1)[0]
    stamped = f"{base}+dev.{sha}"
    _write(path, _sub_once(before, anchor, rf"\g<1>{stamped}\g<3>", str(path)))
    print(f"  DEV   package.json -> {stamped}")
    return 0


def check() -> int:
    """Report what each file claims; non-zero if they disagree."""
    seen: dict[str, str] = {}
    for path, anchor, _value in _targets("0.0.0"):
        if not path.exists():
            print(f"  SKIP  {path} (not found)")
            continue
        m = anchor.search(_read(path))
        if not m:
            print(f"  FAIL  {path.name}: no version found")
            return 1
        seen[path.name] = m.group(2)
        print(f"  {path.name:24} {m.group(2)}")

    # tauri.conf.json is expected to differ (stripped); the rest must agree.
    tauri = seen.pop("tauri.conf.json", None)
    labels = {v.split("+", 1)[0] for v in seen.values()}
    if len(labels) > 1:
        print(f"\nMISMATCH: {seen}")
        return 1
    if labels and tauri is not None:
        want = strip_suffix(next(iter(labels)))
        if tauri != want:
            print(f"\nMISMATCH: tauri.conf.json is {tauri}, expected {want}")
            return 1
    print("\nAll version strings agree.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("version", nargs="?", help="e.g. 0.1.1-alpha")
    ap.add_argument("--check", action="store_true", help="verify, change nothing")
    ap.add_argument("--dev-stamp", metavar="SHA",
                    help="append +dev.SHA to package.json only (CI dispatch builds)")
    args = ap.parse_args()

    if args.dev_stamp:
        return dev_stamp(args.dev_stamp)
    if args.check:
        return check()
    if not args.version:
        ap.error("give a version, --check, or --dev-stamp")
    if not VERSION_RE.match(args.version):
        ap.error(f"not a version label: {args.version!r} (want e.g. 0.1.1-alpha)")
    print(f"Setting version {args.version}")
    apply(args.version)
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
