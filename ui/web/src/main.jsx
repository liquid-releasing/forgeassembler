// ForgeAssembler React entry point.
//
// Icons render as real lucide-react SVG components (see primitives.jsx Icon),
// so there's no `window.lucide.createIcons()` DOM sweep to bridge — the
// `window.lucide?.createIcons?.()` calls left in the ported components are
// harmless no-ops via optional chaining.
import React from 'react';
import { createRoot } from 'react-dom/client';

import './tokens.css'; // chains ./colors_and_type.css via @import
import { App } from './App.jsx';

createRoot(document.getElementById('root')).render(<App />);
