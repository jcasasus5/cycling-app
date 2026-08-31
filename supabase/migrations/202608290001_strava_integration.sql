alter table public.activities
  add column if not exists strava_upload_id text not null default '',
  add column if not exists strava_activity_id text not null default '',
  add column if not exists strava_status text not null default '',
  add column if not exists strava_error text not null default '';

create table if not exists public.strava_connections (
  user_id uuid primary key default auth.uid() references auth.users(id) on delete cascade,
  athlete_id text not null,
  athlete_name text not null,
  access_token_encrypted text not null,
  refresh_token_encrypted text not null,
  expires_at bigint not null,
  connected_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.strava_connections enable row level security;

drop policy if exists strava_connections_owner_all on public.strava_connections;
create policy strava_connections_owner_all on public.strava_connections
  for all to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

grant select, insert, update, delete on public.strava_connections to authenticated;
