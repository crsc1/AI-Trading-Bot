import { defineConfig } from 'vite';
import solid from 'vite-plugin-solid';
import tailwindcss from '@tailwindcss/vite';
import fs from 'fs';
import path from 'path';

// Use HTTPS if mkcert certs exist (fixes Chrome HSTS redirect for localhost)
const certDir = path.resolve(__dirname, 'certs');
const hasCerts = fs.existsSync(path.join(certDir, 'localhost+2.pem'));

export default defineConfig({
  plugins: [solid(), tailwindcss()],
  server: {
    port: 3000,
    ...(hasCerts ? {
      https: {
        cert: fs.readFileSync(path.join(certDir, 'localhost+2.pem')),
        key: fs.readFileSync(path.join(certDir, 'localhost+2-key.pem')),
      },
    } : {}),
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
  worker: {
    format: 'es',
  },
});
