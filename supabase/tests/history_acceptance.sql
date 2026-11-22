-- Run AFTER migrations 001-003 in the team's TEST database SQL Editor.
-- Uses the actual RPCs/triggers and rolls back every test record.
begin;
insert into sentra_memory.projects(project_id,project_name)
values('__history_acceptance__','Synthetic transaction history test');
set constraints all immediate;
set constraints all deferred;

do $$
declare source jsonb; snapshot jsonb; result text; entry jsonb;
begin
 if (public.project_history('__history_acceptance__','2025-09-02T00:00:00Z',null)->'entry') is distinct from 'null'::jsonb
 then raise exception 'FAIL: fabricated pre-capture history'; end if;
 source := jsonb_build_object('source_type','email','source_id','__history_source__',
  'project_id','__history_acceptance__','subject','Synthetic feedback','sender','test@example.test',
  'received_at','2025-09-02T15:00:00Z','body','Please add booking.');
 perform public.capture_source(source);
 snapshot := public.memory_read('__history_acceptance__');
 snapshot := jsonb_set(snapshot,'{deliverables}',jsonb_build_array(jsonb_build_object(
  'id','__history_work__','match_key','booking','title','Booking','description','Synthetic work',
  'status','open','blocked_reason',null,'updated_at',clock_timestamp(),
  'evidence',jsonb_build_array(jsonb_build_object(
   'evidence_id','11111111-1111-4111-8111-111111111111','source_id','__history_source__','kind','requirement')))));
 result := public.memory_commit('__history_acceptance__',0,snapshot,source,
  jsonb_build_array(jsonb_build_object('evidence_id','11111111-1111-4111-8111-111111111111',
   'source_type','email','source_id','__history_source__','kind','requirement',
   'quote','Please add booking.','start',0,'end',char_length('Please add booking.'))),
  '{"action":"ingested","state_changed":true}');
 if result <> 'accepted' then raise exception 'FAIL: memory commit not accepted'; end if;
end; $$;

set constraints all immediate;
do $$
declare historical jsonb; result text; evidence jsonb;
begin
 historical := public.project_history('__history_acceptance__',null,1)->'entry';
 if historical->'snapshot'->'deliverables'->0->>'title' is distinct from 'Booking'
 then raise exception 'FAIL: snapshot did not capture committed work'; end if;
 if (public.project_history('__history_acceptance__',null,0)->'entry'->'snapshot'->'deliverables') is distinct from '[]'::jsonb
 then raise exception 'FAIL: earlier state was overwritten'; end if;
 if (public.project_history('__history_acceptance__','2025-09-03T00:00:00Z',null)->'entry') is distinct from 'null'::jsonb
 then raise exception 'FAIL: source receipt time incorrectly became knowledge time'; end if;
 evidence := public.project_evidence('__history_acceptance__','11111111-1111-4111-8111-111111111111');
 if (evidence->>'span_valid')::boolean is not true then raise exception 'FAIL: source evidence invalid'; end if;
 if public.project_evidence('another-project','11111111-1111-4111-8111-111111111111') is not null
 then raise exception 'FAIL: cross-project evidence leakage'; end if;
 result := public.memory_commit('__history_acceptance__',1,
  public.memory_read('__history_acceptance__'),public.memory_source('email','__history_source__'),
  '[]','{"action":"ingested","state_changed":false}');
 if result <> 'already_processed' then raise exception 'FAIL: replay not idempotent'; end if;
 if (select count(*) from sentra_memory.state_history where project_id='__history_acceptance__') <> 2
 then raise exception 'FAIL: duplicate history on replay'; end if;
 begin
  update sentra_memory.state_history set version=999 where project_id='__history_acceptance__';
  raise exception 'FAIL: history was mutable';
 exception when raise_exception then
  if sqlerrm <> 'Project history is append-only' then raise; end if;
 end;
 if has_function_privilege('anon','public.project_history(text,timestamptz,bigint)','EXECUTE')
 or has_function_privilege('authenticated','public.project_evidence(text,text)','EXECUTE')
 then raise exception 'FAIL: historical RPC exposed to a public role'; end if;
 if not has_function_privilege('service_role','public.project_history(text,timestamptz,bigint)','EXECUTE')
 then raise exception 'FAIL: backend role lacks retrieval access'; end if;
 raise notice 'PASS: actual history capture, prior version, time boundary, evidence isolation and replay';
end; $$;
rollback;
do $$
begin
 if exists(select 1 from sentra_memory.state_history where project_id='__history_acceptance__')
 then raise exception 'FAIL: rolled-back history persisted'; end if;
 raise notice 'PASS: transaction rollback leaves no state history';
end; $$;
