import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, proxy /api to the local server. In prod, nginx handles the same path.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
