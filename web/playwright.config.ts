import { defineConfig } from "@playwright/test";

const fernetKey = "j0aN3s-cLScfv0GfNyG8t0UyONn7y8u2s6o6cLs1hYw=";
const appEnvLiteral = JSON.stringify({
  DISCORD_BOT_TOKEN: "discord-token",
  DISCORD_APPLICATION_ID: "discord-app-id",
  WEB_APP_URL: "http://127.0.0.1:8010",
  CREDENTIALS_ENCRYPTION_KEY: fernetKey,
  SESSION_SECRET_KEY: fernetKey,
});
const encodedAppEnv = Buffer.from(appEnvLiteral, "utf8").toString("base64");

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  use: {
    baseURL: "http://127.0.0.1:8010",
    headless: true,
  },
  webServer: {
    command:
      "npm run build && cd .. && " +
      `uv run python -c \"import base64, json; ` +
      `from pixie_for_pm.config.settings import load_settings; ` +
      `from pixie_for_pm.web.app import create_app; import uvicorn; ` +
      `settings = load_settings(json.loads(base64.b64decode('${encodedAppEnv}'))); ` +
      `uvicorn.run(create_app(settings), host='127.0.0.1', port=8010)\"`,
    port: 8010,
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
