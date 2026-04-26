import { expect, test } from "@playwright/test";

test("install page redirects into Discord bot authorization", async ({
  page,
}) => {
  await page.goto("/");

  await expect(
    page.getByRole("heading", { name: "Install Pixie PM" }),
  ).toBeVisible();

  const installLink = page.getByRole("link", {
    name: "Install Pixie to Discord",
  });

  await expect(installLink).toHaveAttribute("href", "/api/discord/install");

  await Promise.all([
    page.waitForURL(/https:\/\/discord\.com\/oauth2\/authorize/),
    installLink.click(),
  ]);

  const authorizeUrl = new URL(page.url());

  expect(authorizeUrl.searchParams.get("client_id")).toBe("discord-app-id");
  expect(authorizeUrl.searchParams.get("scope")).toBe(
    "bot applications.commands",
  );
  expect(authorizeUrl.searchParams.get("permissions")).toBe("309237713920");
  expect(authorizeUrl.searchParams.get("guild_id")).toBeNull();
  expect(authorizeUrl.searchParams.get("disable_guild_select")).toBeNull();
});
