import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The backend lives under /api and is proxied here, so the browser sees one origin:
// the httpOnly refresh cookie works with no cross-site rules, and the app keeps the
// plain URL space (/tickets/<id> is a page, not an API call).
const API = process.env.VITE_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { "/api": { target: API, changeOrigin: true } },
  },
});
