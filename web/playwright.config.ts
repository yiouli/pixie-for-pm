import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  use: {
    baseURL: "http://127.0.0.1:8010",
    headless: true,
  },
  webServer: {
    command:
      "npm run build && cd .. && uv run python web/tests/e2e/serve_demo_e2e.py",
    port: 8010,
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
