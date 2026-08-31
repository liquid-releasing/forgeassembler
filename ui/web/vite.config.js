import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

const host = process.env.TAURI_DEV_HOST;

// ForgeAssembler's Tauri front-end.
//
// The UI rolls its own primitives and its own small MediaViewer for clip
// thumbnails. It ALSO consumes `forgemoment` for the clip preview — the
// 2,200-line MediaViewer with video / audio / funscript modes, playhead,
// beat overlay and seek-sync that FunscriptForge already uses. Rebuilding
// that here to stay dependency-free was never worth it: setting trim points
// against the real video is the whole job of the preview.
//
// Resolve forgemoment to its SOURCE rather than its built dist/, so edits in
// ../../../forgemoment/src/*.jsx propagate without a rebuild + reinstall.
//
// Array form + regex `find:` because Vite's string aliases are prefix
// matches — a bare `forgemoment` alias rewrites `forgemoment/styles` to
// `<src>/index.js/styles`. Anchored regexes give exact-match per subpath.
// Add an entry here whenever forgemoment exports a new subpath.
const forgemomentRoot = new URL('../../../forgemoment/', import.meta.url);

export default defineConfig({
  plugins: [react({
    // MediaViewer's mounted fiber tree gets very large with clips and
    // timelines active. React Fast Refresh walks it recursively and can
    // overflow the stack during HMR — which this app has ON — so exclude
    // this one shared file and let Vite do a normal module reload instead.
    exclude: /[\\/]forgemoment[\\/]src[\\/]MediaViewer\.jsx$/,
  })],
  clearScreen: false,
  resolve: {
    alias: [
      { find: /^forgemoment\/styles$/, replacement: fileURLToPath(new URL('src/tokens.css', forgemomentRoot)) },
      { find: /^forgemoment$/,         replacement: fileURLToPath(new URL('src/index.js',  forgemomentRoot)) },
    ],
  },
  // Skip the dep-optimizer for forgemoment. Without this, Vite pre-bundles
  // `node_modules/forgemoment/dist/*.js` and serves that — bypassing the
  // alias above and breaking cross-repo HMR.
  optimizeDeps: {
    exclude: ['forgemoment'],
  },
  server: {
    port: 1430,
    strictPort: true,
    host: host || false,
    hmr: host ? { protocol: 'ws', host, port: 1431 } : undefined,
    watch: { ignored: ['**/src-tauri/**'] },
    fs: {
      // Vite restricts file access to the project root by default;
      // forgemoment lives outside ui/web, so whitelist its parent.
      allow: [
        fileURLToPath(new URL('.', import.meta.url)),
        fileURLToPath(new URL('../../../forgemoment', import.meta.url)),
      ],
    },
  },
  envPrefix: ['VITE_', 'TAURI_'],
  build: {
    target: 'esnext',
    minify: 'esbuild',
    sourcemap: true,
  },
});
