-- Additive registry + immutable shared sources; apply after 001.
begin;
create table sentra_memory.customers (
 customer_id text primary key, customer_name text not null,
 status text not null default 'active' check(status in ('active','disabled')),
 created_at timestamptz not null default now()
);
alter table sentra_memory.projects add column customer_id text references sentra_memory.customers;
alter table sentra_memory.projects add column status text not null default 'active' check(status in ('active','disabled'));
alter table sentra_memory.projects add column allowed_senders jsonb not null default '[]';
alter table sentra_memory.projects add column agent_purpose text not null default 'Maintain the client product';
create table sentra_memory.repository_mappings (
 mapping_id text primary key, project_id text not null references sentra_memory.projects,
 provider text not null default 'github' check(provider='github'),
 owner text not null, repository_name text not null, branch text not null default 'main',
 context_path text not null default 'context/CURRENT_STATE.md', active boolean not null default true
);
create unique index unique_active_destination on sentra_memory.repository_mappings
 (lower(owner),lower(repository_name),branch,context_path) where active;
create table sentra_memory.source_projects (
 source_type text not null, source_id text not null,
 project_id text not null references sentra_memory.projects,
 primary key(source_type,source_id,project_id),
 foreign key(source_type,source_id) references sentra_memory.sources
);
insert into sentra_memory.source_projects select source_type,source_id,project_id from sentra_memory.sources;
alter table sentra_memory.sources alter column project_id drop not null;
alter table sentra_memory.evidence drop constraint evidence_project_id_source_type_source_id_fkey;
alter table sentra_memory.evidence add foreign key(source_type,source_id,project_id)
 references sentra_memory.source_projects(source_type,source_id,project_id);
create table sentra_memory.identification_reviews (
 source_type text not null, source_id text not null, candidates jsonb not null,
 reason text not null, status text not null default 'pending' check(status in ('pending','resolved')),
 reviewer text, updated_at timestamptz not null default now(),
 primary key(source_type,source_id), foreign key(source_type,source_id) references sentra_memory.sources
);
create table sentra_memory.sync_status (
 mapping_id text primary key references sentra_memory.repository_mappings,
 version bigint not null, status text not null check(status in ('published','failed','unchanged')),
 updated_at timestamptz not null default now()
);
create or replace function sentra_memory.validate_span() returns trigger
language plpgsql set search_path=pg_catalog as $$
begin
 if not exists(select 1 from sentra_memory.sources s join sentra_memory.source_projects sp
 on (s.source_type,s.source_id)=(sp.source_type,sp.source_id)
 where (sp.project_id,sp.source_type,sp.source_id)=(new.project_id,new.source_type,new.source_id)
 and substring(s.body from new.start_offset+1 for char_length(new.quote))=new.quote)
 then raise exception 'Evidence span does not match authorized project source'; end if;
 return new;
end; $$;
create function public.memory_source_project(p_type text,p_id text,p_project text) returns jsonb
language sql stable security definer set search_path=pg_catalog as $$
 select to_jsonb(s)||jsonb_build_object('project_id',p_project) from sentra_memory.sources s
 join sentra_memory.source_projects sp using(source_type,source_id)
 where sp.source_type=p_type and sp.source_id=p_id and sp.project_id=p_project;
$$;
create function public.capture_source(p_source jsonb) returns text
language plpgsql security definer set search_path=pg_catalog as $$
declare existing sentra_memory.sources;
begin
 insert into sentra_memory.sources(source_type,source_id,project_id,subject,sender,received_at,body)
 values(p_source->>'source_type',p_source->>'source_id',null,p_source->>'subject',p_source->>'sender',
 (p_source->>'received_at')::timestamptz,p_source->>'body') on conflict do nothing;
 if found then return 'accepted'; end if;
 select * into strict existing from sentra_memory.sources
 where source_type=p_source->>'source_type' and source_id=p_source->>'source_id';
 if existing.body<>p_source->>'body' or existing.sender<>p_source->>'sender'
 or existing.subject<>p_source->>'subject' or existing.received_at<>(p_source->>'received_at')::timestamptz
 then raise exception 'Immutable source differs from replay'; end if;
 return 'already_processed';
end; $$;
create function public.context_registry(p_master text) returns jsonb
language sql stable security definer set search_path=pg_catalog as $$
 select jsonb_build_object('master_repository',p_master,
 'customers',coalesce((select jsonb_agg(jsonb_build_object('customer_id',customer_id,
 'customer_name',customer_name,'status',status)) from sentra_memory.customers),'[]'::jsonb),
 'projects',coalesce((select jsonb_agg(jsonb_build_object('project_id',project_id,
 'customer_id',customer_id,'project_name',project_name,'description',project_summary,
 'status',status,'allowed_senders',allowed_senders,'agent_purpose',agent_purpose))
 from sentra_memory.projects where customer_id is not null),'[]'::jsonb),
 'mappings',coalesce((select jsonb_agg(to_jsonb(m)) from sentra_memory.repository_mappings m),'[]'::jsonb));
$$;
create function public.identification_review(p_type text,p_id text,p_candidates jsonb,p_reason text) returns void
language sql security definer set search_path=pg_catalog as $$
 insert into sentra_memory.identification_reviews(source_type,source_id,candidates,reason)
 values(p_type,p_id,p_candidates,p_reason) on conflict do nothing;
$$;
create function public.resolve_identification(p_type text,p_id text,p_reviewer text) returns void
language sql security definer set search_path=pg_catalog as $$
 update sentra_memory.identification_reviews set status='resolved',reviewer=p_reviewer,updated_at=now()
 where source_type=p_type and source_id=p_id;
$$;
create function public.record_sync(p_mapping text,p_version bigint,p_status text) returns void
language sql security definer set search_path=pg_catalog as $$
 insert into sentra_memory.sync_status(mapping_id,version,status) values(p_mapping,p_version,p_status)
 on conflict(mapping_id) do update set version=excluded.version,status=excluded.status,updated_at=now();
$$;
create or replace function public.memory_commit(
    p_project text, p_revision bigint, p_snapshot jsonb, p_source jsonb,
    p_evidence jsonb, p_event jsonb
) returns text
language plpgsql security definer set search_path = pg_catalog as $$
declare
    current_revision bigint;
    existing_project text;
    changed boolean := (p_event->>'state_changed')::boolean;
begin
    select revision into strict current_revision from sentra_memory.projects
    where project_id = p_project for update;

    if current_revision <> p_revision then
        return 'retry';
    end if;

    if p_source is not null and p_source <> 'null'::jsonb then
        insert into sentra_memory.sources
            (source_type, source_id, project_id, subject, sender, received_at, body)
        values (
            p_source->>'source_type', p_source->>'source_id', p_project,
            p_source->>'subject', p_source->>'sender',
            (p_source->>'received_at')::timestamptz, p_source->>'body'
        )
        on conflict (source_type, source_id) do nothing;
        if not exists(select 1 from sentra_memory.sources s
          where s.source_type=p_source->>'source_type' and s.source_id=p_source->>'source_id'
          and s.body=p_source->>'body' and s.sender=p_source->>'sender')
        then raise exception 'Immutable source mismatch'; end if;
        insert into sentra_memory.source_projects(source_type, source_id, project_id)
        values (p_source->>'source_type', p_source->>'source_id', p_project)
        on conflict do nothing;
        if not found then return 'already_processed'; end if;
    end if;

    insert into sentra_memory.evidence
        (evidence_id, project_id, source_type, source_id, kind, quote, start_offset, end_offset)
    select (e->>'evidence_id')::uuid, p_project, e->>'source_type', e->>'source_id',
           e->>'kind', e->>'quote', (e->>'start')::integer, (e->>'end')::integer
    from jsonb_array_elements(p_evidence) as e;

    if exists (
        select 1
        from jsonb_array_elements(
            (p_snapshot->'deliverables') || (p_snapshot->'questions') ||
            (p_snapshot->'decisions') || (p_snapshot->'reviews')
        ) as record
        cross join lateral jsonb_array_elements(record->'evidence') as ref
        where not exists (
            select 1 from sentra_memory.evidence e
            where e.project_id = p_project
              and e.evidence_id = (ref->>'evidence_id')::uuid
              and e.source_id = ref->>'source_id' and e.kind = ref->>'kind'
        )
    ) then
        raise exception 'State references evidence outside the project or of the wrong kind';
    end if;

    insert into sentra_memory.deliverables as target (project_id, id, data)
    select p_project, record->>'id', record
    from jsonb_array_elements(p_snapshot->'deliverables') as record
    on conflict (project_id, id) do update set data = excluded.data
    where target.data is distinct from excluded.data;

    insert into sentra_memory.questions as target (project_id, id, data)
    select p_project, record->>'id', record
    from jsonb_array_elements(p_snapshot->'questions') as record
    on conflict (project_id, id) do update set data = excluded.data
    where target.data is distinct from excluded.data;

    insert into sentra_memory.decisions as target (project_id, id, data)
    select p_project, record->>'id', record
    from jsonb_array_elements(p_snapshot->'decisions') as record
    on conflict (project_id, id) do update set data = excluded.data
    where target.data is distinct from excluded.data;

    insert into sentra_memory.review_queue as target (project_id, id, data)
    select p_project, record->>'id', record
    from jsonb_array_elements(p_snapshot->'reviews') as record
    on conflict (project_id, id) do update set data = excluded.data
    where target.data is distinct from excluded.data;

    update sentra_memory.projects
    set revision = current_revision + 1,
        version = version + case when changed then 1 else 0 end,
        as_of = case when changed then clock_timestamp() else as_of end
    where project_id = p_project;

    insert into sentra_memory.events (project_id, revision, data)
    values (p_project, current_revision + 1, p_event || jsonb_build_object(
        'evidence_ids', coalesce((select jsonb_agg(e->>'evidence_id')
                                  from jsonb_array_elements(p_evidence) as e), '[]'::jsonb)
    ));
    return 'accepted';
end;
$$;


-- No caller-facing grants; authorization is checked by the backend before RPCs.
revoke all on function public.memory_source_project(text,text,text) from public,anon,authenticated;
revoke all on function public.capture_source(jsonb) from public,anon,authenticated;
revoke all on function public.context_registry(text) from public,anon,authenticated;
revoke all on function public.identification_review(text,text,jsonb,text) from public,anon,authenticated;
revoke all on function public.resolve_identification(text,text,text) from public,anon,authenticated;
revoke all on function public.record_sync(text,bigint,text) from public,anon,authenticated;
grant execute on function public.memory_source_project(text,text,text),public.capture_source(jsonb),
 public.context_registry(text),public.identification_review(text,text,jsonb,text),
 public.resolve_identification(text,text,text),public.record_sync(text,bigint,text) to service_role;
alter table sentra_memory.customers enable row level security;
alter table sentra_memory.repository_mappings enable row level security;
alter table sentra_memory.source_projects enable row level security;
alter table sentra_memory.identification_reviews enable row level security;
alter table sentra_memory.sync_status enable row level security;
alter table sentra_memory.projects enable row level security;
alter table sentra_memory.sources enable row level security;
alter table sentra_memory.evidence enable row level security;
alter table sentra_memory.deliverables enable row level security;
alter table sentra_memory.questions enable row level security;
alter table sentra_memory.decisions enable row level security;
alter table sentra_memory.review_queue enable row level security;
alter table sentra_memory.events enable row level security;
commit;
