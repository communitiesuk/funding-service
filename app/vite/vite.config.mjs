/* jshint esversion: 6 */
import { viteStaticCopy } from 'vite-plugin-static-copy';

export default {
  server: {
    port: 3000,
    strictPort: true,
    warmup:{
      clientFiles: ['./src/main.js']
    },
  },

  clearScreen: false,
  appType: 'custom',

  build: {
    manifest: true,
    quietDeps: true,
    cssCodeSplit: false
  },

  resolve: {
    alias: {
      '@': '/src'
    }
  },

  plugins: [
    viteStaticCopy({
      targets: [
        {
          src: 'node_modules/govuk-frontend/dist/govuk/assets/images',
          dest: 'assets/static'
        },
        {
          src: 'node_modules/govuk-frontend/dist/govuk/assets/fonts',
          dest: 'assets/static'
        },
        {
          src: 'node_modules/govuk-frontend/dist/govuk/assets/manifest.json',
          dest: 'assets/static'
        },
        {
          src: 'src/assets/images',
          dest: 'assets/static'
        }
      ]
    })
  ]
};
