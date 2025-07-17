import path from "node:path"
import { viteStaticCopy } from "vite-plugin-static-copy"

import { defineConfig } from "vite"

export default defineConfig({
  base: "/static",
  build: {
    outDir: path.join(__dirname, "app/assets/dist"),
    manifest: "manifest.json",
    rollupOptions: {
      input: ["app/assets/main.scss", "app/assets/main.js"],
      external: [
        /assets\/fonts\/.*\.(woff|woff2)$/,
        /assets\/images\/.*\.svg$/,
      ],
    },
    emptyOutDir: true,
  },
  css: {
    preprocessorOptions: {
      scss: {
        silenceDeprecations: [
          "mixed-decls",
          "global-builtin",
          "slash-div",
          "import",
        ],
      },
    },
  },
  plugins: [
    viteStaticCopy({
      targets: [
        {
          src: "node_modules/govuk-frontend/dist/govuk/assets/*",
          dest: "./assets",
        },
        {
          src: "node_modules/accessible-autocomplete/dist/*",
          dest: "./assets/accessible-autocomplete",
        },
        {
          src: "app/assets/images",
          dest: "./assets"
        }
      ],
    }),
  ],
  clearScreen: false,
  appType: "custom"
})
