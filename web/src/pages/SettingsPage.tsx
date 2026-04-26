import { type ReactNode, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { ApiKeyForm } from "../components/ApiKeyForm";
import { ProviderCard } from "../components/ProviderCard";
import { ApiError, apiFetch } from "../lib/api";
import { getCurrentUser, redirectToDiscordLogin } from "../lib/auth";

type ServerSummary = {
  id: string;
  discord_server_id: string;
  name: string | null;
  owned_by_current_user: boolean;
};

type ConnectionSummary = {
  provider: string;
  status: string;
  connected_at: string;
  last_used_at: string | null;
};

type ProviderDefinition = {
  id: string;
  name: string;
  authType: "oauth2" | "api_key";
  apiKeyFields?: readonly string[];
  helpUrl?: string;
};

const providers: readonly ProviderDefinition[] = [
  { id: "notion", name: "Notion", authType: "oauth2" },
  { id: "github", name: "GitHub", authType: "oauth2" },
  {
    id: "posthog",
    name: "PostHog",
    authType: "api_key",
    apiKeyFields: ["api_key", "project_id", "host"],
    helpUrl: "https://posthog.com/docs/api",
  },
  {
    id: "fireflies",
    name: "Fireflies",
    authType: "api_key",
    apiKeyFields: ["api_key"],
    helpUrl: "https://fireflies.ai/account/integrations",
  },
  { id: "vercel", name: "Vercel", authType: "oauth2" },
  { id: "airtable", name: "Airtable", authType: "oauth2" },
];

export function SettingsPage() {
  const [searchParams] = useSearchParams();
  const serverId = searchParams.get("server_id");
  const connectedProvider = searchParams.get("connected");

  const [loading, setLoading] = useState(true);
  const [busyProvider, setBusyProvider] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [server, setServer] = useState<ServerSummary | null>(null);
  const [connections, setConnections] = useState<ConnectionSummary[]>([]);
  const [expandedProvider, setExpandedProvider] = useState<string | null>(null);
  const [viewerName, setViewerName] = useState<string>("Pixie user");

  const connectionByProvider = useMemo(() => {
    return new Map(
      connections.map((connection) => [connection.provider, connection]),
    );
  }, [connections]);

  useEffect(() => {
    if (!serverId) {
      setLoading(false);
      setError("Missing server_id query parameter.");
      return;
    }

    let cancelled = false;

    async function bootstrap() {
      const currentUser = await getCurrentUser();

      if (!currentUser) {
        redirectToDiscordLogin(window.location);
        return;
      }

      if (cancelled) {
        return;
      }

      const profileName =
        currentUser.display_name ?? currentUser.email ?? "Pixie user";
      setViewerName(profileName);

      try {
        const serverResponse = await apiFetch<ServerSummary>(
          `/api/servers/${serverId}/claim`,
          { method: "POST" },
        );

        if (!serverResponse.owned_by_current_user) {
          throw new Error(
            "This Discord server is already claimed by another account.",
          );
        }

        const connectionResponse = await apiFetch<ConnectionSummary[]>(
          `/api/connections?server_id=${serverId}`,
        );

        if (cancelled) {
          return;
        }

        setServer(serverResponse);
        setConnections(connectionResponse);
        setError(null);
      } catch (caughtError) {
        if (!cancelled) {
          setError(getErrorMessage(caughtError));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void bootstrap();

    return () => {
      cancelled = true;
    };
  }, [serverId]);

  async function refreshConnections() {
    if (!serverId) {
      return;
    }
    const nextConnections = await apiFetch<ConnectionSummary[]>(
      `/api/connections?server_id=${serverId}`,
    );
    setConnections(nextConnections);
  }

  async function handleOAuthConnect(providerId: string) {
    if (!serverId) {
      return;
    }
    setBusyProvider(providerId);
    setError(null);
    try {
      const response = await apiFetch<{ authorize_url: string }>(
        `/api/connections/${providerId}/authorize?server_id=${serverId}&response_mode=json`,
      );
      window.location.assign(response.authorize_url);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError));
      setBusyProvider(null);
    }
  }

  async function handleApiKeySave(
    providerId: string,
    values: Record<string, string>,
  ) {
    if (!serverId) {
      return;
    }
    setBusyProvider(providerId);
    setError(null);
    try {
      await apiFetch(`/api/connections/${providerId}?server_id=${serverId}`, {
        method: "POST",
        body: JSON.stringify(values),
      });
      await refreshConnections();
      setExpandedProvider(null);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError));
    } finally {
      setBusyProvider(null);
    }
  }

  async function handleDisconnect(providerId: string) {
    if (!serverId) {
      return;
    }
    setBusyProvider(providerId);
    setError(null);
    try {
      await apiFetch(`/api/connections/${providerId}?server_id=${serverId}`, {
        method: "DELETE",
      });
      await refreshConnections();
    } catch (caughtError) {
      setError(getErrorMessage(caughtError));
    } finally {
      setBusyProvider(null);
    }
  }

  async function handleLogout() {
    await apiFetch("/api/auth/logout", { method: "POST" });
    window.location.reload();
  }

  if (loading) {
    return (
      <Shell
        title="Loading settings..."
        subtitle="Preparing the integration surface."
      />
    );
  }

  return (
    <Shell
      title="Pixie PM Settings"
      subtitle={
        server ? `Server ${server.discord_server_id}` : "Server settings"
      }
    >
      <div className="flex flex-col gap-10">
        <section className="flex flex-col gap-4 rounded-4xl border border-white/60 bg-white/80 p-6 shadow-[0_24px_80px_rgba(32,54,48,0.12)] backdrop-blur md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-sm uppercase tracking-[0.3em] text-teal-700">
              Workspace
            </p>
            <h1 className="mt-2 text-4xl font-bold text-stone-950">
              {server?.name ?? serverId}
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-stone-600">
              Connect the tools your product team agents can use inside this
              Discord server.
            </p>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-right text-sm text-stone-600">
              <div className="font-semibold text-stone-900">{viewerName}</div>
              <div>Discord-authenticated workspace access</div>
            </div>
            <button
              className="rounded-full border border-stone-300 px-5 py-2 text-sm font-semibold text-stone-700 transition hover:border-stone-400"
              onClick={handleLogout}
              type="button"
            >
              Logout
            </button>
          </div>
        </section>

        {connectedProvider ? (
          <div className="rounded-3xl border border-emerald-200 bg-emerald-50 px-5 py-4 text-sm font-medium text-emerald-800">
            {connectedProvider} connected successfully.
          </div>
        ) : null}

        {error ? (
          <div className="rounded-3xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm font-medium text-rose-800">
            {error}
          </div>
        ) : null}

        <section className="grid gap-4">
          {providers.map((provider) => {
            const connection = connectionByProvider.get(provider.id);
            const isExpanded = expandedProvider === provider.id;
            const busy = busyProvider === provider.id;
            return (
              <ProviderCard
                busy={busy}
                connection={connection}
                key={provider.id}
                onConnect={() => {
                  if (provider.authType === "oauth2") {
                    void handleOAuthConnect(provider.id);
                    return;
                  }
                  setExpandedProvider(isExpanded ? null : provider.id);
                }}
                onDisconnect={() => {
                  void handleDisconnect(provider.id);
                }}
                provider={provider}
              >
                {provider.authType === "api_key" &&
                isExpanded &&
                provider.apiKeyFields ? (
                  <ApiKeyForm
                    busy={busy}
                    fields={provider.apiKeyFields}
                    helpUrl={provider.helpUrl}
                    onCancel={() => setExpandedProvider(null)}
                    onSave={async (values) => {
                      await handleApiKeySave(provider.id, values);
                    }}
                  />
                ) : null}
              </ProviderCard>
            );
          })}
        </section>
      </div>
    </Shell>
  );
}

function Shell({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children?: ReactNode;
}) {
  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,rgba(26,188,156,0.18),transparent_30%),radial-gradient(circle_at_bottom_right,rgba(245,158,11,0.18),transparent_28%),linear-gradient(180deg,#f7f4eb_0%,#eef5f0_100%)] px-4 py-8 text-stone-900 md:px-10">
      <div className="mx-auto max-w-6xl">
        <div className="mb-8 text-center md:text-left">
          <p className="text-sm uppercase tracking-[0.35em] text-stone-500">
            Pixie PM
          </p>
          <h1 className="mt-3 text-5xl font-bold leading-tight">{title}</h1>
          <p className="mt-3 text-lg text-stone-600">{subtitle}</p>
        </div>
        {children}
      </div>
    </main>
  );
}

function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Something went wrong while loading settings.";
}
