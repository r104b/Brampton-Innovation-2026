-- Capture history from this installation forward; do not invent earlier history.
begin;
create table sentra_memory.state_history (
 project_id text not null references sentra_memory.projects,
 revision bigint not null, version bigint not null,
 observed_at timestamptz not null default clock_timestamp(),
 snapshot jsonb not null,
 primary key(project_id,revision)
);
create index history_by_time on sentra_memory.state_history(project_id,observed_at desc,revision desc);
alter table sentra_memory.source_projects add column recorded_at timestamptz not null default clock_timestamp();
alter table sentra_memory.evidence add column recorded_at timestamptz not null default clock_timestamp();
alter table sentra_memory.state_history enable row level security;
create trigger immutable_state_history before update or delete or truncate
on sentra_memory.state_history for each statement execute function sentra_memory.reject_mutation();

-- Backfill only what exists NOW, at the actual capture time, not the old as_of.
insert into sentra_memory.state_history(project_id,revision,version,snapshot)
select project_id,revision,version,public.memory_read(project_id) from sentra_memory.projects;

create function sentra_memory.capture_state_history() returns trigger
language plpgsql security definer set search_path=pg_catalog as $$
declare captured jsonb; current_project sentra_memory.projects;
begin
 if tg_op='UPDATE' and new.revision=old.revision then return new; end if;
 -- Deferred capture sees the FINAL state of the transaction. Intermediate
 -- revisions in one transaction were never externally visible committed state.
 select * into strict current_project from sentra_memory.projects where project_id=new.project_id;
 captured := to_jsonb(current_project) || jsonb_build_object(
  'deliverables',coalesce((select jsonb_agg(r.data order by r.id) from sentra_memory.deliverables r where r.project_id=new.project_id),'[]'::jsonb),
  'questions',coalesce((select jsonb_agg(r.data order by r.id) from sentra_memory.questions r where r.project_id=new.project_id),'[]'::jsonb),
  'decisions',coalesce((select jsonb_agg(r.data order by r.id) from sentra_memory.decisions r where r.project_id=new.project_id),'[]'::jsonb),
  'reviews',coalesce((select jsonb_agg(r.data order by r.id) from sentra_memory.review_queue r where r.project_id=new.project_id),'[]'::jsonb)
 );
 insert into sentra_memory.state_history(project_id,revision,version,snapshot)
 values(new.project_id,current_project.revision,current_project.version,captured)
 on conflict(project_id,revision) do nothing;
 return new;
end; $$;
create constraint trigger capture_project_state after insert or update on sentra_memory.projects
deferrable initially deferred
for each row execute function sentra_memory.capture_state_history();

create function public.project_history(p_project text,p_at timestamptz default null,p_version bigint default null)
returns jsonb language sql stable security definer set search_path=pg_catalog as $$
 select jsonb_build_object(
  'coverage_start',(select min(observed_at) from sentra_memory.state_history where project_id=p_project),
  'entry',(select to_jsonb(h) from sentra_memory.state_history h where project_id=p_project
    and (p_at is null or observed_at<=p_at) and (p_version is null or version=p_version)
    order by observed_at desc,revision desc limit 1)
 );
$$;

-- Time range means ORIGINAL SOURCE RECEIPT time, not historical project state.
-- Return project-specific exact evidence spans only, never the entire email body.
create function public.project_source_evidence(p_project text,p_from timestamptz,p_to timestamptz)
returns jsonb language sql stable security definer set search_path=pg_catalog as $$
 select coalesce(jsonb_agg(row order by row->>'received_at',row->>'source_id',row->>'evidence_id'),'[]'::jsonb)
 from (
  select jsonb_build_object('source_id',s.source_id,'source_type',s.source_type,
   'received_at',s.received_at,'linked_at',sp.recorded_at,
   'evidence_id',e.evidence_id,'kind',e.kind,'quote',left(e.quote,240),
   'evidence_recorded_at',e.recorded_at,
   'span_valid',substring(s.body from e.start_offset+1 for char_length(e.quote))=e.quote) as row
  from sentra_memory.sources s
  join sentra_memory.source_projects sp using(source_type,source_id)
  left join sentra_memory.evidence e on e.project_id=sp.project_id
   and e.source_type=s.source_type and e.source_id=s.source_id
  where sp.project_id=p_project and s.received_at>=p_from and s.received_at<p_to
  order by s.received_at,s.source_id,e.evidence_id limit 201
 ) records;
$$;

create function public.project_evidence(p_project text,p_evidence text) returns jsonb
language sql stable security definer set search_path=pg_catalog as $$
 select jsonb_build_object('evidence_id',e.evidence_id,'source_id',e.source_id,
 'kind',e.kind,'quote',left(e.quote,240),'recorded_at',e.recorded_at,
 'span_valid',substring(s.body from e.start_offset+1 for char_length(e.quote))=e.quote)
 from sentra_memory.evidence e join sentra_memory.sources s using(source_type,source_id)
 where e.project_id=p_project and e.evidence_id::text=p_evidence;
$$;
revoke all on function public.project_history(text,timestamptz,bigint) from public,anon,authenticated;
revoke all on function public.project_source_evidence(text,timestamptz,timestamptz) from public,anon,authenticated;
revoke all on function public.project_evidence(text,text) from public,anon,authenticated;
grant execute on function public.project_history(text,timestamptz,bigint),
 public.project_source_evidence(text,timestamptz,timestamptz),public.project_evidence(text,text) to service_role;
commit;
