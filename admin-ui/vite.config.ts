import { defineConfig } from "vite";

export default defineConfig({
  root: ".",
  build: {
    outDir: "../backend/static/dist",
    emptyOutDir: true,
    cssCodeSplit: false,
    minify: "esbuild",
    rollupOptions: {
      input: "src/admin-entry.ts",
      output: {
        entryFileNames: "admin.js",
        assetFileNames: (info) => {
          if (info.name && info.name.endsWith(".css")) {
            return "admin.css";
          }
          return "[name][extname]";
        },
      },
    },
  },
});
