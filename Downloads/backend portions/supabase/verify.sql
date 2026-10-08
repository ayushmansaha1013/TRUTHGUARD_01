-- =============================================================================
-- Quick verification script — run AFTER schema.sql to confirm the security
-- posture is actually in place (paste into Supabase SQL Editor).
-- Useful as evidence/screenshots for the project report.
-- =============================================================================

-- 1. RLS must be enabled AND forced on both tables.
select
  schemaname,
  tablename,
  rowsecurity   as rls_enabled,
  forcerowsecurity as rls_forced
from pg_tables
where schemaname = 'public'
  and tablename in ('profiles', 'scan_logs');
-- EXPECTED: rls_enabled = true, rls_forced = true for BOTH rows.


-- 2. Every policy that governs access.
select
  schemaname,
  tablename,
  policyname,
  cmd,
  roles::text,
  qual          as using_expression,
  with_check    as with_check_expression
from pg_policies
where schemaname = 'public'
order by tablename, cmd, policyname;
-- EXPECTED (6 rows):
--   profiles  SELECT  profiles_select_own             using (id = auth.uid())
--   profiles  SELECT  educators_select_all_profiles   using (role = 'educator')
--   profiles  UPDATE  profiles_update_own             using + with_check (id = auth.uid())
--   scan_logs SELECT  students_select_own_scan_logs   own rows AND role = student
--   scan_logs SELECT  educators_select_all_scan_logs  role = educator
--   scan_logs INSERT  users_insert_own_scan_logs      with_check (user_id = auth.uid())
-- CRITICAL: there must be NO UPDATE and NO DELETE policy on scan_logs.
--           Their absence is what makes the audit trail append-only (Part C.6).
-- CRITICAL: there must be NO INSERT policy on profiles for clients — rows are
--           created only by the handle_new_user() trigger.


-- 3. The signup trigger must exist on auth.users.
select trigger_name, event_manipulation, action_timing, action_statement
from information_schema.triggers
where event_object_schema = 'auth' and event_object_table = 'users';
-- EXPECTED: on_auth_user_created | INSERT | AFTER | EXECUTE FUNCTION handle_new_user()


-- 4. SECURITY DEFINER functions must have a pinned search_path.
--    An unpinned search_path on a SECURITY DEFINER function is a
--    privilege-escalation vector (schema shadowing).
select
  p.proname                                        as function_name,
  p.prosecdef                                      as security_definer,
  coalesce(a.config::text, 'NOT SET — FIX THIS')   as search_path
from pg_proc p
join pg_namespace n on n.oid = p.pronamespace
left join pg_db_role_setting s on s.setrole = 0 and s.setdatabase = 0
left join lateral (
  select array_agg(x) as config
  from unnest(s.setconfig) as x
  where x like 'search_path%'
) a on true
where n.nspname = 'public'
  and p.proname in ('handle_new_user', 'set_my_role', 'current_user_role',
                    'enforce_role_immutable', 'jwt_role')
order by p.proname;
-- EXPECTED: security_definer = true (except jwt_role) and
--           search_path = {search_path=public, pg_temp} for every definer function.


-- 5. The dashboard view must be security_invoker (otherwise it bypasses RLS).
select
  viewname,
  (pg_catalog.pg_get_viewdef(('public.' || viewname)::regclass, true) like '%') as defined,
  c.reloptions::text as options
from pg_views v
join pg_class c on c.oid = ('public.' || v.viewname)::regclass
where v.schemaname = 'public' and v.viewname = 'educator_scan_logs';
-- EXPECTED: options contains {security_invoker=true}


-- 6. Anon role must NOT be able to read the tables or the view.
select
  grantee,
  table_name,
  string_agg(privilege_type, ', ' order by privilege_type) as privileges
from information_schema.role_table_grants
where table_schema = 'public'
  and table_name in ('profiles', 'scan_logs', 'educator_scan_logs')
group by grantee, table_name
order by table_name, grantee;
-- EXPECTED: no row with grantee = 'anon'.


-- 7. Sanity check on stored data.
select role, count(*) from public.profiles group by role;
select content_type, verdict, count(*) from public.scan_logs
group by content_type, verdict order by 3 desc;
