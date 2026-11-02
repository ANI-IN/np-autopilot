-- Reverses 0028: seed colours back (only where 0028's colour is still set),
-- and kb.audit_log out of the Realtime publication.
update kb.node_types t set color = v.old_color
from (values
    ('program', '#7c3aed', '#b45309'), ('course', '#2563eb', '#1d4ed8'), ('domain', '#4f46e5', '#0e7490'),
    ('module', '#0891b2', '#0f766e'), ('week', '#0d9488', '#15803d'), ('session', '#ea580c', '#c2410c'),
    ('topic', '#059669', '#4d7c0f'), ('instructor', '#d97706', '#be123c'), ('process', '#db2777', '#475569')
) as v(key, old_color, new_color)
where t.key = v.key and lower(t.color) = v.new_color;

do $$
begin
    if exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime'
               and schemaname = 'kb' and tablename = 'audit_log') then
        execute 'alter publication supabase_realtime drop table kb.audit_log';
    end if;
end $$;
