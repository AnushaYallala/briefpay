import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  esbuild: { jsx: "automatic" },
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  test: {
    environment: "jsdom",
    globals: true,
    include: ["tests/**/*.test.{ts,tsx}"],
    restoreMocks: true,
    env: { NEXT_PUBLIC_DEMO_MODE: "true", NEXT_PUBLIC_API_BASE_URL: "http://api.test/api" },
  },
});
