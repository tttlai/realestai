import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vitejs.dev/config/
export default defineConfig({
  base: '/',
  plugins: [react()],
  optimizeDeps: {
    exclude: ['lucide-react'],
  },
  build: {
    // GitHub Pages serves the repo's top-level docs/ folder on main, so build straight into it.
    // Everything in public/ (CNAME, legal pages, icon) is copied over on each build.
    outDir: '../docs',
    emptyOutDir: true,
  },
});
