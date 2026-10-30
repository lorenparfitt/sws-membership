import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// API calls go to the local backend in development; production serves both behind one host.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
});
