-- 0031 down: remove the schedule and its two functions. The extensions
-- (pg_cron, pg_net) are left in place: Supabase projects commonly use them for
-- other jobs, and dropping pg_cron would delete every other job. Drop them by
-- hand (Database -> Extensions) if nothing else needs them.
do $$
begin
    if to_regnamespace('cron') is not null then
        perform kb.sync_schedule_remove();
    end if;
end $$;
drop function if exists kb.sync_schedule_install(text, text);
drop function if exists kb.sync_schedule_remove();
