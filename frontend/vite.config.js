import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react-swc';

// Vite-конфиг для фронта Map v12:
//  - React для сложных панелей (аналитика, чат и т.п.);
//  - сборка в ../static/dist с manifest для Flask;
//  - один основной entry: src/main.js.
export default defineConfig({
  root: '.',
  plugins: [react()],
  build: {
    manifest: true,
    outDir: '../static/dist',
    emptyOutDir: true,
    rollupOptions: {
      input: 'src/main.js'
    }
  },
  server: {
    port: 5173,
    strictPort: true
  }
});
