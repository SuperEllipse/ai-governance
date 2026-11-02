import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run dev` proxies API calls to a locally running `python applications/web_app.py`.
const apiTarget = process.env.API_TARGET ?? "http://127.0.0.1:8090";

export default defineConfig({
  plugins: [react()],
  // Relative asset URLs so the built app works behind Cloudera proxies and path prefixes.
  base: "./",
  server: {
    proxy: { "/api": apiTarget },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
