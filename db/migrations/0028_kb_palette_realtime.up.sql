-- 0028 — accessible, non-purple type colours; Realtime for the change feed.
--
-- Colours: the built-in types move to one accessible palette (the same list
-- web/lib/kb/typedefs.py PALETTE offers for custom types). Only rows still
-- holding their 0022/0026 seed colour are changed; an admin's choice is kept.
--
-- Realtime (D2): kb.audit_log joins the supabase_realtime publication so the
-- browser can be told "something changed" over a socket. Realtime applies the
-- subscriber's RLS (audit_log_select) to every change it forwards; the
-- browser then fetches the rows through /api/kb/changes as before. Skipped
-- where the publication does not exist (plain Postgres).
update kb.node_types t set color = v.new_color
from (values
    ('program', '#7c3aed', '#b45309'), ('course', '#2563eb', '#1d4ed8'), ('domain', '#4f46e5', '#0e7490'),
    ('module', '#0891b2', '#0f766e'), ('week', '#0d9488', '#15803d'), ('session', '#ea580c', '#c2410c'),
    ('topic', '#059669', '#4d7c0f'), ('instructor', '#d97706', '#be123c'), ('process', '#db2777', '#475569')
) as v(key, old_color, new_color)
where t.key = v.key and lower(t.color) = v.old_color;

do $$
begin
    if exists (select 1 from pg_publication where pubname = 'supabase_realtime')
       and not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime'
                       and schemaname = 'kb' and tablename = 'audit_log') then
        execute 'alter publication supabase_realtime add table kb.audit_log';
    end if;
end $$;
