
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],

  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,

    // Cloudflare 외부 접속 허용
    allowedHosts: [
      "knows-pair-toddler-enabled.trycloudflare.com",
    ],

    // React API 요청을 FastAPI로 전달
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
