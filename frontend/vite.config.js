import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev-сервер на :3000, доступен извне контейнера (host 0.0.0.0).
// Прокси /api и /ws на backend, чтобы фронт ходил на тот же origin.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 3000,
    proxy: {
      "/api": { target: "http://backend:8000", changeOrigin: true },
      "/ws": { target: "ws://backend:8000", ws: true },
    },
  },
});
