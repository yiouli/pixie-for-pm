import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ProviderCard } from "./ProviderCard";

const PROVIDER = {
  id: "github",
  name: "GitHub",
  authType: "oauth2" as const,
};

const BASE_CONNECTION = {
  provider: "github",
  status: "active",
  connected_at: "2026-01-01T00:00:00+00:00",
  last_used_at: null,
};

function render(props: Parameters<typeof ProviderCard>[0]) {
  return renderToStaticMarkup(createElement(ProviderCard, props));
}

describe("ProviderCard – expired token (no refresh token, past expiry)", () => {
  const expiredAt = new Date(Date.now() - 60_000).toISOString();
  const connection = { ...BASE_CONNECTION, access_expires_at: expiredAt };

  it("shows a red dot", () => {
    const markup = render({
      provider: PROVIDER,
      connection,
      busy: false,
      onConnect: () => {},
      onDisconnect: () => {},
    });
    expect(markup).toContain("bg-rose-500");
  });

  it("shows 'Access expired' text", () => {
    const markup = render({
      provider: PROVIDER,
      connection,
      busy: false,
      onConnect: () => {},
      onDisconnect: () => {},
    });
    expect(markup).toContain("Access expired");
  });

  it("shows a Reconnect button instead of Disconnect", () => {
    const markup = render({
      provider: PROVIDER,
      connection,
      busy: false,
      onConnect: () => {},
      onDisconnect: () => {},
    });
    expect(markup).toContain("Reconnect");
    expect(markup).not.toContain("Disconnect");
  });
});

describe("ProviderCard – expiring token (no refresh token, future expiry)", () => {
  const expiresAt = new Date(Date.now() + 30 * 60_000).toISOString();
  const connection = { ...BASE_CONNECTION, access_expires_at: expiresAt };

  it("shows an amber dot", () => {
    const markup = render({
      provider: PROVIDER,
      connection,
      busy: false,
      onConnect: () => {},
      onDisconnect: () => {},
    });
    expect(markup).toContain("bg-amber-400");
  });

  it("shows 'Access expires at' text", () => {
    const markup = render({
      provider: PROVIDER,
      connection,
      busy: false,
      onConnect: () => {},
      onDisconnect: () => {},
    });
    expect(markup).toContain("Access expires at");
  });

  it("shows a Disconnect button (not Reconnect)", () => {
    const markup = render({
      provider: PROVIDER,
      connection,
      busy: false,
      onConnect: () => {},
      onDisconnect: () => {},
    });
    expect(markup).toContain("Disconnect");
    expect(markup).not.toContain("Reconnect");
  });
});

describe("ProviderCard – active token with refresh token", () => {
  it("shows a green dot and Disconnect button", () => {
    const markup = render({
      provider: PROVIDER,
      connection: BASE_CONNECTION,
      busy: false,
      onConnect: () => {},
      onDisconnect: () => {},
    });
    expect(markup).toContain("bg-emerald-500");
    expect(markup).toContain("Disconnect");
  });
});

describe("ProviderCard – not connected", () => {
  it("shows a grey dot and Connect button", () => {
    const markup = render({
      provider: PROVIDER,
      connection: undefined,
      busy: false,
      onConnect: () => {},
      onDisconnect: () => {},
    });
    expect(markup).toContain("bg-stone-300");
    expect(markup).toContain("Connect");
  });
});
