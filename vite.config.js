import path from "node:path";
import { viteStaticCopy } from "vite-plugin-static-copy";

import { defineConfig } from "vite";

export default defineConfig({
    base: "/static",
    build: {
        outDir: path.join(__dirname, "app/assets/dist"),
        manifest: "manifest.json",
        rollupOptions: {
            input: [
                "app/assets/main.scss",
                "app/assets/main.js",
                "app/assets/admin.scss",
                "app/assets/js/cookie-consent/index.js",
            ],
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
                loadPaths: ["node_modules/govuk-frontend/dist"],
                quietDeps: true,
                silenceDeprecations: [
                    "global-builtin",
                    "slash-div",
                    "color-functions",
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
                    src: "app/assets/images",
                    dest: "./assets",
                },
            ],
        }),
    ],
    test: {
        globals: true,
        setupFiles: ["app/assets/test/setup.js"],
    },
    clearScreen: false,
    appType: "custom",
});
