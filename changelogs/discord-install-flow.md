# Discord Install Flow

- added a dedicated callback-less Discord bot install route at `/api/discord/install` that generates the correct `bot applications.commands` authorize URL without hardcoding the target guild
- added install-specific settings (`DISCORD_APPLICATION_ID`, `DISCORD_INSTALL_PERMISSIONS`) with fallback to `DISCORD_OAUTH_CLIENT_ID` when the same Discord app is used for login and bot install
- added a root landing page that exposes the install CTA and explains the `/settings` handoff needed after authorization
- added backend regression tests for the install redirect contract and a Playwright browser test that clicks through the landing page into Discord's authorize URL
- updated README, specs, and the Discord e2e guide so local setup and manual verification use the new browser install flow instead of a hand-built Developer Portal URL
