-- Напоминания push-уведомлением (применено в проекте 10.10.2026).
-- Значения ключей и список разрешённых аккаунтов в репозиторий не попадают:
-- они вписаны прямо в базу (private.push_config, private.push_allowed).
create extension if not exists pg_cron;
create extension if not exists pg_net;

create schema if not exists private;
revoke all on schema private from public, anon, authenticated;
create table private.push_config (key text primary key, value text not null);   -- vapid_public, vapid_private, vapid_subject, cron_secret
create table private.push_allowed (user_id uuid not null, app text not null, primary key (user_id, app));

create table public.push_subs (
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  app text not null check (app = 'kartuli'),
  endpoint text not null,
  p256dh text not null,
  auth text not null,
  enabled boolean not null default true,
  remind_at time not null default '19:00',
  tz text not null default 'Asia/Tbilisi',
  last_day date,
  last_sent_at timestamptz,
  updated_at timestamptz not null default now(),
  primary key (user_id, app)
);
alter table public.push_subs enable row level security;

create or replace function public.push_allowed(p_app text)
returns boolean language sql stable security definer set search_path = ''
as $$ select exists (select 1 from private.push_allowed a where a.user_id = auth.uid() and a.app = p_app) $$;
revoke all on function public.push_allowed(text) from public, anon;
grant execute on function public.push_allowed(text) to authenticated;

create policy push_subs_select on public.push_subs for select to authenticated
  using (user_id = (select auth.uid()));
create policy push_subs_insert on public.push_subs for insert to authenticated
  with check (user_id = (select auth.uid()) and public.push_allowed(app));
create policy push_subs_update on public.push_subs for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()) and public.push_allowed(app));
create policy push_subs_delete on public.push_subs for delete to authenticated
  using (user_id = (select auth.uid()));
grant select, insert, update, delete on public.push_subs to authenticated;

create or replace function public.push_config()
returns jsonb language sql stable security definer set search_path = ''
as $$ select coalesce(jsonb_object_agg(key, value), '{}'::jsonb) from private.push_config $$;
revoke all on function public.push_config() from public, anon, authenticated;
grant execute on function public.push_config() to service_role;

create or replace function public.push_allowed_users()
returns table (user_id uuid, app text) language sql stable security definer set search_path = ''
as $$ select user_id, app from private.push_allowed $$;
revoke all on function public.push_allowed_users() from public, anon, authenticated;
grant execute on function public.push_allowed_users() to service_role;

select cron.schedule('kartuli-push', '*/10 * * * *', $$
  select net.http_post(
    url := 'https://lvkjktepfspbmwfyldxm.supabase.co/functions/v1/kartuli-push',
    headers := jsonb_build_object('Content-Type', 'application/json',
      'x-cron-secret', (select value from private.push_config where key = 'cron_secret')),
    body := '{}'::jsonb, timeout_milliseconds := 30000)
$$);
