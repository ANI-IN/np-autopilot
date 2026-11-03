-- 0031: the schedule of the KB sync, on the DATABASE side (run 5, Part 4).
--
-- Design (docs/DEPLOYMENT.md "Scheduled sync"): pg_cron in this Supabase
-- project fires on a cron expression (hourly by default, configurable) and,
-- with pg_net, POSTs to the deployment's /api/cron/kb-sync with
-- "Authorization: Bearer <secret>". The secret lives in Supabase Vault under
-- the name 'kb_sync_secret' (the same value as the deployment's
-- KB_SYNC_SECRET) and is read when the job fires, so it never appears in the
-- job's text. The work itself runs in the deployment (web/lib/kb/sync.py),
-- time-boxed below the function limit; the next tick continues.
--
-- Why not Vercel Cron: it fires on Production deployments only (a preview,
-- i.e. the dev deployment, would never sync), and a Hobby plan allows one run
-- a day. One design here serves dev and production alike.
--
-- Additive: the extensions are created only where they are available and
-- allowed (pg_cron lives in the database named by cron.database_name: on
-- Supabase that is `postgres`); elsewhere this only adds the two functions,
-- which then say the scheduler is not available. The functions are for the
-- OWNER (operators); nobody else may run them.

do $$
begin
    if exists (select 1 from pg_available_extensions where name = 'pg_net') then
        create extension if not exists pg_net;
    else
        raise notice 'pg_net is not available here: the sync schedule cannot be installed in this database';
    end if;
    if exists (select 1 from pg_available_extensions where name = 'pg_cron')
       and current_database() = coalesce(current_setting('cron.database_name', true), 'postgres') then
        create extension if not exists pg_cron;
    else
        raise notice 'pg_cron is not available in this database: the sync schedule cannot be installed here';
    end if;
end $$;

-- Install (or replace) the schedule. p_endpoint: the deployment's
-- https://<host>/api/cron/kb-sync ; p_cron: a cron expression (default hourly).
create or replace function kb.sync_schedule_install(p_endpoint text, p_cron text default '0 * * * *')
returns bigint
language plpgsql security definer set search_path = pg_catalog, public
as $fn$
declare job bigint;
begin
    if to_regnamespace('cron') is null or to_regnamespace('net') is null then
        raise exception 'pg_cron and pg_net are needed for the sync schedule (Supabase: Database -> Extensions)';
    end if;
    if p_endpoint !~ '^https://[^/\s]+/api/cron/kb-sync$' and p_endpoint !~ '^http://(127\.0\.0\.1|localhost|host\.docker\.internal)(:[0-9]+)?/api/cron/kb-sync$' then
        raise exception 'the endpoint must be https://<deployment>/api/cron/kb-sync';
    end if;
    if to_regnamespace('vault') is null
       or not exists (select 1 from vault.secrets where name = 'kb_sync_secret') then
        raise exception 'store the secret first: select vault.create_secret(''<KB_SYNC_SECRET>'', ''kb_sync_secret'')';
    end if;
    -- A Vercel PREVIEW deployment sits behind Deployment Protection: the call
    -- then also carries Vercel's "Protection Bypass for Automation" secret,
    -- when one is stored in Vault as 'kb_sync_vercel_bypass' (read at fire
    -- time too). Production needs none.
    execute 'select cron.schedule($1, $2, $3)' into job using 'kb-sync', p_cron, format(
        $job$select net.http_post(url := %L,
                 headers := jsonb_strip_nulls(jsonb_build_object(
                     'authorization', 'Bearer ' || (select decrypted_secret from vault.decrypted_secrets where name = 'kb_sync_secret'),
                     'x-vercel-protection-bypass', (select decrypted_secret from vault.decrypted_secrets where name = 'kb_sync_vercel_bypass'),
                     'content-type', 'application/json')),
                 body := '{}'::jsonb, timeout_milliseconds := 60000)$job$, p_endpoint);
    return job;
end;
$fn$;

create or replace function kb.sync_schedule_remove() returns boolean
language plpgsql security definer set search_path = pg_catalog, public
as $fn$
declare n int := 0;
begin
    if to_regnamespace('cron') is null then
        return false;
    end if;
    execute 'select count(*) from cron.job where jobname = ''kb-sync''' into n;
    if n > 0 then
        execute 'select cron.unschedule(''kb-sync'')';
    end if;
    return n > 0;
end;
$fn$;

revoke all on function kb.sync_schedule_install(text, text) from public;
revoke all on function kb.sync_schedule_remove() from public;
do $$
begin
    if exists (select 1 from pg_roles where rolname = 'authenticated') then
        execute 'revoke all on function kb.sync_schedule_install(text, text) from authenticated, anon';
        execute 'revoke all on function kb.sync_schedule_remove() from authenticated, anon';
    end if;
end $$;
