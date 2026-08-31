-- Existing routes remain private; public means visible to signed-in users only.
alter table public.routes add column is_public boolean not null default false;
create index routes_public_created_idx on public.routes (created_at desc, id desc) where is_public;

-- The existing owner policies remain the only policies that permit writes.
create policy routes_public_read on public.routes
  for select to authenticated using (is_public);
create policy route_segments_public_read on public.route_segments
  for select to authenticated using (exists (
    select 1 from public.routes
    where routes.id = route_segments.route_id and routes.is_public
  ));

-- Keep all recorded activities, including when a private route is deleted.
alter table public.activities add column route_name text;
update public.activities a set route_name = r.name from public.routes r where r.id = a.route_id;
alter table public.activities alter column route_name set not null;
alter table public.activities alter column route_id drop not null;
alter table public.activities drop constraint activities_route_id_fkey;
alter table public.activities add constraint activities_route_id_fkey
  foreign key (route_id) references public.routes(id) on delete set null;

-- Snapshot the name while the route is readable. Deletion preserves the snapshot.
create or replace function public.snapshot_activity_route_name()
returns trigger language plpgsql security invoker set search_path = '' as $$
begin
  if new.route_id is not null then
    if tg_op = 'INSERT' then
      select name into new.route_name from public.routes where id = new.route_id;
    elsif new.route_id is distinct from old.route_id then
      select name into new.route_name from public.routes where id = new.route_id;
    end if;
  end if;
  return new;
end;
$$;
create trigger activities_snapshot_route_name
  before insert or update of route_id on public.activities
  for each row execute function public.snapshot_activity_route_name();
revoke execute on function public.snapshot_activity_route_name() from public, anon;

alter policy activities_owner_all on public.activities
  using ((select auth.uid()) = user_id)
  with check (
    (select auth.uid()) = user_id and (
      route_id is null or exists (
        select 1 from public.routes
        where routes.id = activities.route_id
          and (routes.user_id = (select auth.uid()) or routes.is_public)
      )
    )
  );

create or replace function public.create_route(draft jsonb)
returns bigint
language plpgsql
security invoker
set search_path = public
as $$
declare
  new_route_id bigint;
  segment jsonb;
begin
  if auth.uid() is null then
    raise exception 'authentication required';
  end if;

  insert into public.routes (
    user_id, name, distance_km, elevation_gain_m, start_altitude_m,
    end_altitude_m, avg_grade_percent, max_grade_percent, original_image_path, is_public
  ) values (
    auth.uid(),
    draft->>'name',
    (draft->>'distance_km')::double precision,
    (draft->>'elevation_gain_m')::double precision,
    (draft->>'start_altitude_m')::double precision,
    (draft->>'end_altitude_m')::double precision,
    (draft->>'avg_grade_percent')::double precision,
    (draft->>'max_grade_percent')::double precision,
    nullif(draft->>'original_image_path', ''),
    coalesce((draft->>'is_public')::boolean, false)
  )
  returning id into new_route_id;

  for segment in select value from jsonb_array_elements(draft->'segments')
  loop
    insert into public.route_segments (
      route_id, start_km, end_km, grade_percent, start_altitude_m, end_altitude_m
    ) values (
      new_route_id,
      (segment->>'start_km')::double precision,
      (segment->>'end_km')::double precision,
      (segment->>'grade_percent')::double precision,
      (segment->>'start_altitude_m')::double precision,
      (segment->>'end_altitude_m')::double precision
    );
  end loop;

  return new_route_id;
end;
$$;

create or replace function public.update_route(target_route_id bigint, draft jsonb)
returns boolean
language plpgsql
security invoker
set search_path = public
as $$
declare
  segment jsonb;
begin
  update public.routes set
    name = draft->>'name',
    distance_km = (draft->>'distance_km')::double precision,
    elevation_gain_m = (draft->>'elevation_gain_m')::double precision,
    start_altitude_m = (draft->>'start_altitude_m')::double precision,
    end_altitude_m = (draft->>'end_altitude_m')::double precision,
    avg_grade_percent = (draft->>'avg_grade_percent')::double precision,
    max_grade_percent = (draft->>'max_grade_percent')::double precision,
    original_image_path = nullif(draft->>'original_image_path', ''),
    is_public = coalesce((draft->>'is_public')::boolean, false)
  where id = target_route_id and user_id = auth.uid();

  if not found then
    return false;
  end if;

  delete from public.route_segments where route_id = target_route_id;
  for segment in select value from jsonb_array_elements(draft->'segments')
  loop
    insert into public.route_segments (
      route_id, start_km, end_km, grade_percent, start_altitude_m, end_altitude_m
    ) values (
      target_route_id,
      (segment->>'start_km')::double precision,
      (segment->>'end_km')::double precision,
      (segment->>'grade_percent')::double precision,
      (segment->>'start_altitude_m')::double precision,
      (segment->>'end_altitude_m')::double precision
    );
  end loop;
  return true;
end;
$$;

create or replace function public.duplicate_route(target_route_id bigint)
returns bigint language plpgsql security invoker set search_path = public as $$
declare
  source_draft jsonb;
begin
  -- Read the route and all segments in one snapshot, even if its owner edits it.
  select to_jsonb(r) || jsonb_build_object(
    'name', r.name || ' copia',
    'is_public', false,
    'segments', (select jsonb_agg(to_jsonb(s) order by s.start_km, s.id)
                 from public.route_segments s where s.route_id = r.id)
  ) into source_draft
  from public.routes r
  where r.id = target_route_id and (r.user_id = auth.uid() or r.is_public);
  if not found then
    return null;
  end if;
  -- create_route always assigns the authenticated user, never the source owner.
  return public.create_route(source_draft);
end;
$$;

revoke execute on function public.create_route(jsonb) from public, anon;
revoke execute on function public.update_route(bigint, jsonb) from public, anon;
revoke execute on function public.duplicate_route(bigint) from public, anon;
grant execute on function public.create_route(jsonb) to authenticated;
grant execute on function public.update_route(bigint, jsonb) to authenticated;
grant execute on function public.duplicate_route(bigint) to authenticated;
