import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { WorkspaceHeader } from "./SettingsPage";

describe("WorkspaceHeader", () => {
  it("renders the Discord server name and icon when guild metadata exists", () => {
    const markup = renderToStaticMarkup(
      createElement(WorkspaceHeader, {
        fallbackServerId: "1459772566528069715",
        onLogout: () => {},
        server: {
          discord_server_id: "1459772566528069715",
          icon_url:
            "https://cdn.discordapp.com/icons/1459772566528069715/abcdef0123456789.png?size=128",
          id: "server-1",
          name: "BlueSoul",
          owned_by_current_user: true,
        },
        viewerName: "BlueSoul",
      }),
    );

    expect(markup).toContain("BlueSoul");
    expect(markup).toContain("BlueSoul server icon");
    expect(markup).toContain(
      "https://cdn.discordapp.com/icons/1459772566528069715/abcdef0123456789.png?size=128",
    );
    expect(markup).not.toContain("1459772566528069715</h1>");
  });
});
