// The one place the app's version comes from.
//
// `__APP_VERSION__` is replaced at build time by vite.config.js with the
// version in package.json, which `scripts/bump_version.py` writes along
// with Cargo.toml, Cargo.lock and tauri.conf.json. Nothing here is typed
// by hand: three hardcoded strings in the UI once claimed v0.2.0-alpha
// while every version file said 0.1.0-alpha.
//
// CI stamps a dispatch build `<version>+dev.<sha>`, so a test build shows
// its provenance in the window instead of looking like a release.
const APP_VERSION = typeof __APP_VERSION__ === 'string' ? __APP_VERSION__ : '0.0.0-dev';

// "0.1.0-alpha"      -> "Alpha 0.1.0"
// "0.1.0-alpha+dev.a1b2c3d" -> "Alpha 0.1.0+dev.a1b2c3d"
function versionLabel(v = APP_VERSION) {
  const [core, ...restParts] = v.split('-');
  const rest = restParts.join('-');
  if (!rest) return core;
  const [tag, ...build] = rest.split('+');
  const suffix = build.length ? `+${build.join('+')}` : '';
  const pretty = tag.charAt(0).toUpperCase() + tag.slice(1);
  return `${pretty} ${core}${suffix}`;
}

const APP_VERSION_LABEL = versionLabel();

export { APP_VERSION, APP_VERSION_LABEL, versionLabel };
