-- Server-only project memory. Public RPCs are callable by service_role only.
create schema sentra_memory;
revoke all on schema sentra_memory from public;

create table sentra_memory.projects (
    project_id text primary key,
    project_name text not null,
    project_summary text not null default '',
    client_senders jsonb not null default '[]',
    version bigint not null default 0 check (version >= 0),
    revision bigint not null default 0 check (revision >= 0),
    as_of timestamptz not null default now()
);

create table sentra_memory.sources (
    source_type text not null check (source_type in ('email', 'meeting', 'qa_report')),
    source_id text not null check (source_id <> ''),
    project_id text not null references sentra_memory.projects,
    subject text not null,
    sender text not null,
    received_at timestamptz not null,
    body text not null,
    primary key (source_type, source_id),
    unique (project_id, source_type, source_id)
);

create table sentra_memory.evidence (
    evidence_id uuid primary key,
    project_id text not null,
    source_type text not null,
    source_id text not null,
    kind text not null check (kind in ('requirement', 'implementation', 'qa_result', 'client_answer', 'decision')),
    quote text not null check (length(trim(quote)) > 0),
    start_offset integer not null check (start_offset >= 0),
    end_offset integer not null check (end_offset = start_offset + char_length(quote)),
    foreign key (project_id, source_type, source_id)
        references sentra_memory.sources (project_id, source_type, source_id)
);

create table sentra_memory.deliverables (
    project_id text not null references sentra_memory.projects,
    id text not null,
    data jsonb not null check (data->>'id' = id),
    primary key (project_id, id)
);

create table sentra_memory.questions (
    project_id text not null references sentra_memory.projects,
    id text not null,
    data jsonb not null check (data->>'id' = id),
    primary key (project_id, id)
);

create table sentra_memory.decisions (
    project_id text not null references sentra_memory.projects,
    id text not null,
    data jsonb not null check (data->>'id' = id),
    primary key (project_id, id)
);

create table sentra_memory.review_queue (
    project_id text not null references sentra_memory.projects,
    id text not null,
    data jsonb not null check (data->>'id' = id),
    primary key (project_id, id)
);

create table sentra_memory.events (
    id bigint generated always as identity primary key,
    project_id text not null references sentra_memory.projects,
    revision bigint not null,
    created_at timestamptz not null default now(),
    data jsonb not null,
    unique (project_id, revision)
);

create function sentra_memory.reject_mutation() returns trigger
language plpgsql set search_path = pg_catalog as $$
begin
    raise exception 'Project history is append-only';
end;
$$;

create trigger immutable_sources
before update or delete or truncate on sentra_memory.sources
for each statement execute function sentra_memory.reject_mutation();

create trigger immutable_evidence
before update or delete or truncate on sentra_memory.evidence
for each statement execute function sentra_memory.reject_mutation();

create trigger immutable_events
before update or delete or truncate on sentra_memory.events
for each statement execute function sentra_memory.reject_mutation();

create function sentra_memory.validate_span() returns trigger
language plpgsql set search_path = pg_catalog as $$
begin
    if not exists (
        select 1 from sentra_memory.sources s
        where (s.project_id, s.source_type, s.source_id) =
              (new.project_id, new.source_type, new.source_id)
          and substring(s.body from new.start_offset + 1 for char_length(new.quote)) = new.quote
    ) then
        raise exception 'Evidence span does not match the project source';
    end if;
    return new;
end;
$$;

create trigger valid_evidence_span before insert on sentra_memory.evidence
for each row execute function sentra_memory.validate_span();

create function public.memory_read(p_project text) returns jsonb
language sql stable security definer set search_path = pg_catalog as $$
    select to_jsonb(p) || jsonb_build_object(
        'deliverables', coalesce((
            select jsonb_agg(r.data order by r.id) from sentra_memory.deliverables r
            where r.project_id = p.project_id
        ), '[]'::jsonb),
        'questions', coalesce((
            select jsonb_agg(r.data order by r.id) from sentra_memory.questions r
            where r.project_id = p.project_id
        ), '[]'::jsonb),
        'decisions', coalesce((
            select jsonb_agg(r.data order by r.id) from sentra_memory.decisions r
            where r.project_id = p.project_id
        ), '[]'::jsonb),
        'reviews', coalesce((
            select jsonb_agg(r.data order by r.id) from sentra_memory.review_queue r
            where r.project_id = p.project_id
        ), '[]'::jsonb)
    )
    from sentra_memory.projects p where p.project_id = p_project;
$$;

create function public.memory_source(p_type text, p_id text) returns jsonb
language sql stable security definer set search_path = pg_catalog as $$
    select to_jsonb(s) from sentra_memory.sources s
    where s.source_type = p_type and s.source_id = p_id;
$$;

create function public.memory_commit(
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
        if not found then
            select project_id into strict existing_project from sentra_memory.sources
            where source_type = p_source->>'source_type' and source_id = p_source->>'source_id';
            if existing_project = p_project then
                return 'already_processed';
            end if;
            return 'foreign_source';
        end if;
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

revoke all on function public.memory_read(text) from public, anon, authenticated;
grant execute on function public.memory_read(text) to service_role;
revoke all on function public.memory_source(text, text) from public, anon, authenticated;
grant execute on function public.memory_source(text, text) to service_role;
revoke all on function public.memory_commit(text, bigint, jsonb, jsonb, jsonb, jsonb) from public, anon, authenticated;
grant execute on function public.memory_commit(text, bigint, jsonb, jsonb, jsonb, jsonb) to service_role;
