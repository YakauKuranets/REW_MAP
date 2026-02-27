import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './index.css';
import { initPmtiles } from './vendor/pmtilesSetup';

initPmtiles();

const container = document.getElementById('root');
const root = createRoot(container);
root.render(<App />);

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js');
  });
}
