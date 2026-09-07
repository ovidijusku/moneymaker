import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The API is proxied rather than called cross-origin, so there is no CORS
// policy to loosen -- in dev or in the nginx image.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.API_URL ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
