import { ReactNode } from "react";

type ConnectionSummary = {
  provider: string;
  status: string;
  connected_at: string;
  last_used_at: string | null;
};

type ProviderCardProps = {
  provider: {
    id: string;
    name: string;
    authType: "oauth2" | "api_key";
  };
  connection?: ConnectionSummary;
  busy: boolean;
  onConnect: () => void;
  onDisconnect: () => void;
  children?: ReactNode;
};

export function ProviderCard({
  provider,
  connection,
  busy,
  onConnect,
  onDisconnect,
  children,
}: ProviderCardProps) {
  const connected = Boolean(connection);

  return (
    <article className="rounded-4xl border border-white/60 bg-white/85 p-5 shadow-[0_20px_60px_rgba(38,54,44,0.08)] backdrop-blur">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <span
              className={`h-3 w-3 rounded-full ${connected ? "bg-emerald-500" : "bg-stone-300"}`}
            />
            <h2 className="text-xl font-semibold text-stone-900">{provider.name}</h2>
          </div>
          <p className="text-sm text-stone-600">
            {connected
              ? `Connected ${new Date(connection!.connected_at).toLocaleString()}`
              : provider.authType === "oauth2"
                ? "OAuth connection"
                : "API key connection"}
          </p>
        </div>
        <div className="flex gap-3">
          {connected ? (
            <button
              className="rounded-full border border-stone-300 px-5 py-2 text-sm font-semibold text-stone-700 transition hover:border-stone-400 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={busy}
              onClick={onDisconnect}
              type="button"
            >
              Disconnect
            </button>
          ) : (
            <button
              className="rounded-full bg-teal-700 px-5 py-2 text-sm font-semibold text-white transition hover:bg-teal-600 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={busy}
              onClick={onConnect}
              type="button"
            >
              Connect
            </button>
          )}
        </div>
      </div>
      {children}
    </article>
  );
}
