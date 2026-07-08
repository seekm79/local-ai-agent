import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Bind the dev server to localhost only. Proxy /api and /ws to the backend so
// the frontend can use same-origin relative URLs.
export default defineConfig({
  plugins: [react()],
  // Ensure a single React instance across app + markdown deps.
  resolve: { dedupe: ["react", "react-dom"] },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8010", changeOrigin: true },
      "/ws": { target: "ws://127.0.0.1:8010", ws: true },
    },
  },
});
