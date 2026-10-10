-- Напоминания грузинской версии — всем (10.10): список private.push_allowed
-- для 'kartuli' больше не нужен; для других приложений он по-прежнему решает.
create or replace function public.push_allowed(p_app text)
returns boolean language sql stable security definer set search_path = ''
as $$ select auth.uid() is not null and (p_app = 'kartuli'
  or exists (select 1 from private.push_allowed a where a.user_id = auth.uid() and a.app = p_app)) $$;

create or replace function public.push_allowed_users()
returns table (user_id uuid, app text) language sql stable security definer set search_path = ''
as $$ select user_id, app from private.push_allowed
      union select user_id, app from public.push_subs where app = 'kartuli' $$;
