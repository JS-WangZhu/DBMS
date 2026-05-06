import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    host: "0.0.0.0",
    allowedHosts: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:5000",
        // Keep original Host so backend sees real access address (e.g. 192.168.x.x),
        // avoiding generated links/status that incorrectly show 127.0.0.1.
        changeOrigin: false,
        xfwd: true,
      },
    },
  },
});
