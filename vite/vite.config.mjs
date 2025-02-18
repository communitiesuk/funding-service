/* jshint esversion: 6 */

import { viteStaticCopy } from 'vite-plugin-static-copy';

export default {
  server: {
    port: 3000,
    strictPort: true,
  },

  build: {
    manifest: true
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
          src: 'node_modules/govuk-frontend/dist/govuk/assets/fonts',
          dest: 'assets/static'
        },
        {
          src: 'node_modules/govuk-frontend/dist/govuk/assets/images',
          dest: 'assets/static'
        },
        {
          src: 'node_modules/govuk-frontend/dist/govuk/assets/manifest.json',
          dest: 'assets/static'
        }
      ]
    })
  ]
};
