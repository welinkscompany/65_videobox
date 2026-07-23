import { defineConfig, loadEnv } from "vite";
import { configDefaults } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => {
  const fakeApiPort = Number(loadEnv(mode, "", "").PLAYWRIGHT_FAKE_API_PORT ?? 8000);

  return {
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": "/src" } },
  server: {
    proxy: {
      "/api": `http://127.0.0.1:${fakeApiPort}`,
      "/health": `http://127.0.0.1:${fakeApiPort}`,
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./vitest.setup.ts",
    exclude: [...configDefaults.exclude, "e2e/**"],
  },
  };
});
