-- Run only against a disposable database with the repository migrations applied.
-- Fixtures and assertions roll back together; no production data is required.
begin;
create function pg_temp.check_that(ok boolean, description text) returns void
language plpgsql as $$ begin
  if ok is distinct from true then raise exception 'FAILED: %', description; end if;
  raise notice 'PASS: %', description;
end $$;
create temp table fixtures (key text primary key, value jsonb);
grant all on fixtures to authenticated;
insert into auth.users (id) values
  ('a0000000-0000-0000-0000-000000000001'),
  ('b0000000-0000-0000-0000-000000000002');
insert into fixtures values ('draft', '{"name":"Puerto original","distance_km":1,"elevation_gain_m":50,
  "start_altitude_m":100,"end_altitude_m":150,"avg_grade_percent":5,"max_grade_percent":5,
  "segments":[{"start_km":0,"end_km":1,"grade_percent":5,"start_altitude_m":100,"end_altitude_m":150}]}');
set local role authenticated;
set local request.jwt.claim.sub = 'a0000000-0000-0000-0000-000000000001';
insert into fixtures select 'public', to_jsonb(public.create_route(value || '{"is_public":true}')) from fixtures where key='draft';
insert into fixtures select 'private', to_jsonb(public.create_route(value)) from fixtures where key='draft';
select pg_temp.check_that((select count(*) = 2 from routes), 'creator sees both routes');
select pg_temp.check_that((select count(*) = 1 from routes where not is_public), 'private by default');
insert into fixtures select 'activity_draft', jsonb_build_object(
  'route_id', value, 'started_at','2026-08-31T10:00:00Z','ended_at','2026-08-31T10:01:00Z',
  'status','partial','active_seconds',60,'total_seconds',60,'distance_km',0.5,
  'avg_power_w',200,'max_power_w',220,'avg_cadence_rpm',85,'avg_speed_kph',30,'completed_elevation_m',25,
  'samples','[{"timestamp_ms":1,"elapsed_seconds":60,"km":0.5,"speed_kph":30,"cadence_rpm":85,"power_w":200,"grade_percent":5,"altitude_m":125,"paused":false}]'::jsonb
) from fixtures where key='public';
insert into fixtures select 'private_activity', to_jsonb(public.create_activity(
  (select value from fixtures where key='activity_draft') || jsonb_build_object('route_id',value)
)) from fixtures where key='private';

set local request.jwt.claim.sub = 'b0000000-0000-0000-0000-000000000002';
select pg_temp.check_that((select count(*) = 1 from routes), 'other user sees public but not private route');
select pg_temp.check_that((select count(*) = 1 from route_segments), 'public segments readable');
select pg_temp.check_that((select count(*) = 0 from activities), 'owner activities remain private');
select pg_temp.check_that((select count(*) = 0 from activity_samples), 'owner samples remain private');
select pg_temp.check_that(not public.update_route((select value::bigint from fixtures where key='public'),
  (select value from fixtures where key='draft')), 'public route cannot be edited through RPC');
with changed as (update routes set name='unauthorized' returning id)
select pg_temp.check_that((select count(*) = 0 from changed), 'direct route update denied');
with changed as (delete from routes returning id)
select pg_temp.check_that((select count(*) = 0 from changed), 'direct route deletion denied');
with changed as (update route_segments set grade_percent=99 returning id)
select pg_temp.check_that((select count(*) = 0 from changed), 'direct segment update denied');
with changed as (delete from route_segments returning id)
select pg_temp.check_that((select count(*) = 0 from changed), 'direct segment deletion denied');
do $$ begin
  begin
    insert into route_segments(route_id,start_km,end_km,grade_percent,start_altitude_m,end_altitude_m)
    select value::bigint,1,2,0,150,150 from fixtures where key='public';
    raise exception 'FAILED: foreign segment insertion accepted';
  exception when insufficient_privilege then null; end;
  begin
    perform public.create_activity((select value from fixtures where key='activity_draft') ||
      jsonb_build_object('route_id',(select value from fixtures where key='private')));
    raise exception 'FAILED: activity on inaccessible private route accepted';
  exception when insufficient_privilege or not_null_violation then null; end;
end $$;
select pg_temp.check_that(public.duplicate_route((select value::bigint from fixtures where key='private')) is null,
  'private route cannot be duplicated by other users');
insert into fixtures select 'copy', to_jsonb(public.duplicate_route(value::bigint)) from fixtures where key='public';
select pg_temp.check_that((select not is_public and user_id=auth.uid() and name='Puerto original copia'
  from routes where id=(select value::bigint from fixtures where key='copy')), 'duplicate is private and belongs to copier');
select pg_temp.check_that((select count(*) = 1 from route_segments where route_id=(select value::bigint from fixtures where key='copy')),
  'duplicate keeps segments');
select pg_temp.check_that(public.update_route((select value::bigint from fixtures where key='copy'),
  (select value || '{"name":"Mi ruta"}' from fixtures where key='draft')), 'copier can edit duplicate');
select pg_temp.check_that((select name='Puerto original' from routes where id=(select value::bigint from fixtures where key='public')),
  'editing duplicate does not change original');
do $$ begin
  begin
    update routes set user_id='a0000000-0000-0000-0000-000000000001'
    where id=(select value::bigint from fixtures where key='copy');
    raise exception 'FAILED: ownership reassignment accepted';
  exception when insufficient_privilege then null; end;
end $$;
insert into fixtures select 'public_activity', to_jsonb(public.create_activity(value)) from fixtures where key='activity_draft';
select pg_temp.check_that(public.update_activity((select value::bigint from fixtures where key='public_activity'),
  (select value || '{"status":"completed"}' from fixtures where key='activity_draft')), 'public route activity can be resumed and completed');
select pg_temp.check_that((select count(*) = 1 from activity_samples), 'rider can read own samples');

set local request.jwt.claim.sub = 'a0000000-0000-0000-0000-000000000001';
select pg_temp.check_that((select count(*)=1 from activities), 'route creator cannot see other rider activity');
update routes set is_public=false where id=(select value::bigint from fixtures where key='public');
set local request.jwt.claim.sub = 'b0000000-0000-0000-0000-000000000002';
select pg_temp.check_that((select count(*)=0 from routes where id=(select value::bigint from fixtures where key='public')),
  'unsharing removes access to original');
select pg_temp.check_that((select count(*)=1 from activities where route_name='Puerto original'), 'history survives unsharing');
select pg_temp.check_that((select count(*)=1 from activity_samples), 'samples survive unsharing');
select pg_temp.check_that(public.duplicate_route((select value::bigint from fixtures where key='public')) is null,
  'unshared original can no longer be duplicated');

set local request.jwt.claim.sub = 'a0000000-0000-0000-0000-000000000001';
update routes set is_public=true where id=(select value::bigint from fixtures where key='public');
delete from routes where id in (select value::bigint from fixtures where key in ('public','private'));
select pg_temp.check_that((select count(*)=1 from activities where route_id is null and route_name='Puerto original'),
  'deleting private route keeps creator history');
select pg_temp.check_that((select count(*)=1 from activity_samples), 'deleting private route keeps samples');
set local request.jwt.claim.sub = 'b0000000-0000-0000-0000-000000000002';
select pg_temp.check_that((select count(*)=1 from activities where route_id is null and route_name='Puerto original' and status='completed'),
  'deleting public route keeps other rider history');
select pg_temp.check_that((select count(*)=1 from activity_samples), 'deleting public route keeps other rider samples');
select pg_temp.check_that((select count(*)=1 from routes where name='Mi ruta'), 'independent copy survives original deletion');
delete from routes where id=(select value::bigint from fixtures where key='copy');
select pg_temp.check_that((select count(*)=0 from routes), 'copier can delete own copy');

set local role anon;
do $$ begin
  begin
    perform 1 from public.routes;
    raise exception 'FAILED: unauthenticated table access accepted';
  exception when insufficient_privilege then null; end;
  begin
    perform public.duplicate_route(1);
    raise exception 'FAILED: unauthenticated duplicate accepted';
  exception when insufficient_privilege then null; end;
end $$;
rollback;
