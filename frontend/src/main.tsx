import '@fontsource/roboto/400.css';
import '@fontsource/roboto/500.css';
import '@fontsource/roboto/700.css';
import '@fontsource/roboto-mono/400.css';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { App } from './App';
import './styles/tokens.css';
import './styles/base.css';
import './styles/layout.css';
import './styles/components.css';
import './styles/pages.css';
import './styles/sidePanel.css';
import './styles/markdown.css';
import './styles/requests.css';
import './styles/phone.css';
import { themeController } from './utilities/themeController';

themeController.applyStoredChoice();

const rootElement = document.getElementById('root');
if (rootElement === null) {
  throw new Error('The page has no #root element.');
}
createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
