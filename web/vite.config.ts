import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [sveltekit()],
  server: {
    proxy: {
      '/health': 'http://127.0.0.1:8000',
      '/tasks': 'http://127.0.0.1:8000',
      '/file_parse': 'http://127.0.0.1:8000',
      '/service': 'http://127.0.0.1:8000',
      '/openapi.json': 'http://127.0.0.1:8000',
      '/v1': 'http://127.0.0.1:8000'
    }
  },
  optimizeDeps: {
    exclude: ['pdfjs-dist']
  }
});
