-- 0005 — profiles, and the member / recruiting policies.
--
-- WRITTEN BEFORE THERE IS ANYTHING TO PROTECT, deliberately. D3 projected zero
-- sensitive nodes, so a policy failure right now costs nothing. Once the 277
-- hiring rejections land, testing a deny policy means risking exposure of the
-- very rows the policy exists to hide. The order is the safety measure.
--
-- NAMING: DECISIONS §D calls the lower tier `viewer`; the E3 brief calls it
-- `member`. Same role. `member` is used here and in docs/AUTH.md, and §D's
-- `viewer` should be read as an alias for it.
--
-- RLS is the layer that holds when the others are misconfigured (§D), so it
-- goes in before anything can reach the database over HTTP.

-- ---------------------------------------------------------------------------
-- profiles — identity, the VERIFIED domain, and the role.
--
-- `email_domain` is the `hd` claim from a Google Workspace token whose
-- signature and audience were checked server-side. It is NOT parsed from the
-- email address: a Google account can carry an @interviewkickstart.com email
-- without belonging to the Workspace, which is exactly the gap that makes
-- email.endsWith() insufficient (§D).
-- ---------------------------------------------------------------------------
create table profiles (
    user_id      uuid primary key,
    email        text not null,
    email_domain text not null,
    role         text not null default 'member',
    is_shared_account boolean not null default false,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now(),

    constraint role_is_known check (role in ('member', 'recruiting', 'admin')),
    -- The domain rule, in the database. An API route that forgot to check, or a
    -- middleware matcher that stopped matching, cannot create a row that
    -- bypasses this.
    constraint domain_is_ik check (email_domain = 'interviewkickstart.com')
);

create index profiles_role_idx on profiles (role);

alter table profiles enable row level security;

-- A profile is readable only by its owner. Nobody enumerates the user list.
create policy profiles_self_select on profiles
    for select to authenticated
    using (user_id = auth.uid());

-- ---------------------------------------------------------------------------
-- Role helper. SECURITY DEFINER so a caller who cannot read `profiles` can
-- still have their own role resolved — without it, every policy would need the
-- caller to be able to read the table the policy is protecting.
--
-- search_path is pinned: a SECURITY DEFINER function with a mutable search_path
-- is a privilege-escalation primitive.
-- ---------------------------------------------------------------------------
create or replace function np_role() returns text
language sql stable security definer set search_path = public, pg_temp
as $$
    select coalesce((select p.role from profiles p where p.user_id = auth.uid()),
                    'none')
$$;

comment on function np_role() is
    'The caller''s role from profiles, or ''none'' when there is no profile. '
    '''none'' is the default so an unknown identity gets nothing rather than '
    'falling through to a permissive branch.';

create or replace function np_can_see_sensitive() returns boolean
language sql stable
as $$
    select np_role() in ('recruiting', 'admin')
$$;

-- ---------------------------------------------------------------------------
-- The policies.
--
-- SELECT only. Nothing reaches these tables over HTTP with anything else, and
-- an INSERT policy nobody needs is an INSERT policy nobody reviews.
--
-- Two policies per table rather than one with an OR. Postgres ORs multiple
-- permissive policies together, so the effect is identical — but each policy
-- states one rule, and a reader can check "what does a member see" without
-- untangling a boolean.
-- ---------------------------------------------------------------------------

-- nodes: a member sees the non-sensitive graph; recruiting additionally sees
-- the hiring funnel.
create policy nodes_member_select on nodes
    for select to authenticated
    using (not sensitive and np_role() <> 'none');

create policy nodes_recruiting_select on nodes
    for select to authenticated
    using (sensitive and np_can_see_sensitive());

-- edges: visible only when BOTH endpoints are. An edge whose target is hidden
-- would otherwise leak the existence and id of a withheld node.
create policy edges_select on edges
    for select to authenticated
    using (
        np_role() <> 'none'
        and exists (select 1 from nodes n where n.id = edges.source_id)
        and exists (select 1 from nodes n where n.id = edges.target_id)
    );

-- node_sources: provenance follows its node.
create policy node_sources_select on node_sources
    for select to authenticated
    using (
        np_role() <> 'none'
        and exists (select 1 from nodes n where n.id = node_sources.node_id)
    );

-- Reference data: any signed-in profile may read it. It carries no personal
-- data — type names, edge names, file paths and sheet counts.
create policy node_types_select on node_types
    for select to authenticated using (np_role() <> 'none');
create policy edge_rels_select on edge_rels
    for select to authenticated using (np_role() <> 'none');
create policy files_select on files
    for select to authenticated using (np_role() <> 'none');
create policy projection_meta_select on projection_meta
    for select to authenticated using (np_role() <> 'none');

-- Curation tables get NO policy in this phase. E3 is read-only and there is no
-- curation UI, so `authenticated` reaches none of them — default deny stands.
-- A policy added "ready for later" is a policy nobody tested.

grant usage on schema public to authenticated;
grant select on nodes, edges, node_sources, node_types, edge_rels, files,
               projection_meta, profiles to authenticated;
