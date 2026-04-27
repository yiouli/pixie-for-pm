import { expect, test } from "@playwright/test";

const workspaceId = "1459772566528069715";

type TranscriptMessage = {
  agent: string;
  content: string;
};

type DemoLoopResponse = {
  discord_server_id: string;
  channel_id: number;
  thread_key: string;
  first_turn: TranscriptMessage[];
  second_turn: TranscriptMessage[];
};

type DemoLoopDiscordResponse = {
  visible_messages: string[];
};

test("runs the full retention demo agent loop with auth bypass", async ({
  page,
  request,
}) => {
  await page.goto(`/settings?server_id=${workspaceId}`);

  const notionCard = page
    .locator("article")
    .filter({ has: page.getByRole("heading", { name: "Notion" }) });
  const vercelCard = page
    .locator("article")
    .filter({ has: page.getByRole("heading", { name: "Vercel" }) });

  await expect(
    page.getByRole("heading", { name: "Career Growth Demo Lab" }),
  ).toBeVisible();
  await expect(notionCard).toContainText("Connected");
  await expect(vercelCard).toContainText("Connected");

  const response = await request.post("/api/e2e/demo-loop");
  expect(response.ok()).toBeTruthy();

  const payload = (await response.json()) as DemoLoopResponse;

  expect(payload.discord_server_id).toBe(workspaceId);
  expect(payload.channel_id).toBe(1459772566528069715);
  expect(payload.thread_key).toContain("discord-thread-demo-loop");

  expect(payload.first_turn.map((message) => message.agent)).toEqual([
    "product_manager",
    "product_manager",
  ]);
  await expect
    .soft(payload.first_turn[0]?.content ?? "")
    .toContain("Here's how I'm thinking about this");
  await expect
    .soft(payload.first_turn[0]?.content ?? "")
    .toContain("user researcher");
  await expect
    .soft(payload.first_turn[1]?.content ?? "")
    .toContain("three hypotheses");
  await expect
    .soft(payload.first_turn[1]?.content ?? "")
    .toContain("Which direction do you want me to deepen");

  expect(payload.second_turn.map((message) => message.agent)).toEqual([
    "product_manager",
  ]);
  await expect
    .soft(payload.second_turn[0]?.content ?? "")
    .toContain("clickable Vercel prototype");
  await expect
    .soft((payload.second_turn[0]?.content ?? "").toLowerCase())
    .toContain("review the prototype flow");

  const discordResponse = await request.post("/api/e2e/demo-loop-discord");
  expect(discordResponse.ok()).toBeTruthy();

  const discordPayload =
    (await discordResponse.json()) as DemoLoopDiscordResponse;

  expect(discordPayload.visible_messages.length).toBeGreaterThanOrEqual(2);
  await expect
    .soft(discordPayload.visible_messages[0] ?? "")
    .toContain("Here's how I'm thinking about this");
  await expect
    .soft((discordPayload.visible_messages[0] ?? "").toLowerCase())
    .toContain("user researcher");
  await expect
    .soft((discordPayload.visible_messages[1] ?? "").toLowerCase())
    .toContain("three hypotheses");
});
