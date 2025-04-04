import path from "node:path";
import { viteStaticCopy } from "vite-plugin-static-copy";

import { defineConfig } from "vite";

export default defineConfig({
  // I think try and:
  // set the base to /static/ so that it lines up with when its then asking for paths
  // from Flask

  // root: path.join(__dirname, './app/assets/'),
  // base: "/static",
  // base: "/",
  build: {
    outDir: path.join(__dirname, "app/assets/dist"),
    manifest: "manifest.json",
    rollupOptions: {
      input: ["app/assets/main.scss", "app/assets/main.js"],
      // input: ["main.scss", "main.js"]

      // external: [
        // /assets\/fonts\/.*\.(woff|woff2)$/,
        // /assets\/images\/.*\.svg$/,
      // ],
    },
    emptyOutDir: true,
    copyPublicDir: false
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
        // logger: {
        // warn: () => {},
        // },
        // silenceDeprecations: true,
        // quietDeps: true,

        // includePaths: [path.join(__dirname, 'node_modules')]
      },
    },
  },
  plugins: [

    viteStaticCopy({
      targets: [
        {
          src: "node_modules/govuk-frontend/dist/govuk/assets/*",
          // src: "./../../node_modules/govuk-frontend/dist/govuk/assets/*",
          dest: "./assets",
        },
        {
          // src: "./images",
          src: "app/assets/images",
          dest: "./assets"
        }
      ],
    }),
  ],
  // resolve: {
  //   alias: {
  //     '@': '/src'
  //   }
  // },
});
