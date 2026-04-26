create extension if not exists pgcrypto;

create table public.servers (
  id uuid primary key default gen_random_uuid(),
  discord_server_id text not null unique,
  owner_user_id uuid not null references auth.users(id) on delete cascade,
  name text,
  created_at timestamptz not null default now()
);

create unique index idx_servers_discord on public.servers(discord_server_id);
create index idx_servers_owner on public.servers(owner_user_id);

create table public.connections (
  id uuid primary key default gen_random_uuid(),
  server_id uuid not null references public.servers(id) on delete cascade,
  provider text not null,
  credentials_encrypted text not null,
  scopes text[],
  status text not null default 'active',
  connected_at timestamptz not null default now(),
  last_used_at timestamptz,
  unique(server_id, provider)
);

create index idx_connections_server on public.connections(server_id);

alter table public.servers enable row level security;
create policy "users own servers" on public.servers
  for all using (owner_user_id = auth.uid());

alter table public.connections enable row level security;
create policy "users own server connections" on public.connections
  for all using (
    server_id in (select id from public.servers where owner_user_id = auth.uid())
  );
