import globals from 'globals';

// ForgeAssembler UI lint config.
//
// This exists for ONE rule above all: `no-undef`.
//
// Vite and rollup do not fail on an identifier that is referenced but never
// imported or declared. A bare `foo` compiles to a bare `foo` and becomes a
// runtime ReferenceError — and if it sits inside a component that only
// renders once real data arrives, neither `npm run build` nor a test suite
// that never mounts a component will ever see it.
//
// That happened twice in one sitting while the Build canvas was being cut
// down: deleting a dead `ChannelChip` also removed `_MULTI_AXIS` and
// `_DEVICE_META`, and narrowing an import list dropped `channelName`. Both
// built clean, both passed 133 tests, and both crashed the window the
// instant a scene row rendered.
//
// The JSX pragma: this app's files use the automatic JSX runtime via
// @vitejs/plugin-react, so `React` need not be in scope for JSX — but every
// file imports it anyway and uses it directly (React.Fragment,
// React.useState), so no special casing is needed.
export default [
  {
    files: ['**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: {
        ...globals.browser,
        // Replaced at build time by vite.config.js from package.json.
        __APP_VERSION__: 'readonly',
      },
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    linterOptions: {
      reportUnusedDisableDirectives: true,
    },
    rules: {
      // The rule this config is for.
      'no-undef': 'error',

      // An unused import is usually the other half of a bad cut: a symbol
      // left behind after its consumer was deleted. Warn rather than error
      // so it never blocks a release build, and ignore the conventional
      // leading-underscore opt-out.
      'no-unused-vars': ['warn', {
        args: 'none',
        varsIgnorePattern: '^_',
        caughtErrors: 'none',
        ignoreRestSiblings: true,
      }],

      // Real bugs, cheap to check.
      'no-dupe-keys': 'error',
      'no-dupe-args': 'error',
      'no-unreachable': 'error',
      'no-const-assign': 'error',
      'no-self-assign': 'error',
      'use-isnan': 'error',
      'valid-typeof': 'error',
    },
  },
  {
    // Vite config and this file run in Node, not the browser.
    files: ['vite.config.js', 'eslint.config.js'],
    languageOptions: { globals: { ...globals.node } },
  },
  {
    ignores: ['dist/**', 'node_modules/**', 'src-tauri/**', 'convert_esm.py'],
  },
];
