// ForgeAssembler React entry point.
//
// The extracted UI uses the vanilla-lucide DOM pattern: components render
// `<i data-lucide="name">` placeholders and call `window.lucide.createIcons()`
// in an effect to swap them for SVGs. We bridge that global here so the
// prototype's icon code runs unchanged under Vite/ESM (and fully offline,
// instead of the CDN <script> the standalone HTML used).
import React from 'react';
import { createRoot } from 'react-dom/client';
import { createIcons, icons } from 'lucide';

import './tokens.css'; // chains ./colors_and_type.css via @import
import { App } from './App.jsx';

window.lucide = {
  createIcons: (opts) => createIcons({ icons, ...(opts || {}) }),
};

createRoot(document.getElementById('root')).render(<App />);
