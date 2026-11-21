-- Fictional baseline from section 2 of the shared sample pack.
begin;
insert into sentra_memory.projects (project_id, project_name, project_summary, client_senders, as_of)
values ('maple-grove-demo', 'Online Appointment Booking System',
        'Fictional appointment booking system for Maple Grove Dental Clinic.',
        '["jordan.lee@example.test"]', '2026-11-17T14:00:00Z');

insert into sentra_memory.sources
    (source_type, source_id, project_id, subject, sender, received_at, body)
values ('meeting', 'BASELINE-001', 'maple-grove-demo', 'Synthetic project baseline',
        'sample-pack', '2026-11-17T14:00:00Z', E'Patient registration and sign-in\nBrowse available appointment slots\nBook an appointment\nCancel an appointment\nSMS booking confirmations\nStaff admin dashboard\nWhich SMS provider should be used?\nWhat wording should SMS confirmation contain?\nUse React, FastAPI and PostgreSQL for demo architecture.');

insert into sentra_memory.evidence
    (evidence_id, project_id, source_type, source_id, kind, quote, start_offset, end_offset)
values ('00000000-0000-4000-8000-000000000001', 'maple-grove-demo', 'meeting', 'BASELINE-001',
        'requirement', 'Patient registration and sign-in', 0, 32);
insert into sentra_memory.deliverables (project_id, id, data)
values ('maple-grove-demo', 'D-001', '{"id":"D-001","updated_at":"2026-11-17T14:00:00Z","match_key":"patient registration and sign in","evidence":[{"evidence_id":"00000000-0000-4000-8000-000000000001","source_id":"BASELINE-001","kind":"requirement"}],"title":"Patient registration and sign-in","description":"","status":"in_progress","blocked_reason":null}');

insert into sentra_memory.evidence
    (evidence_id, project_id, source_type, source_id, kind, quote, start_offset, end_offset)
values ('00000000-0000-4000-8000-000000000002', 'maple-grove-demo', 'meeting', 'BASELINE-001',
        'requirement', 'Browse available appointment slots', 33, 67);
insert into sentra_memory.deliverables (project_id, id, data)
values ('maple-grove-demo', 'D-002', '{"id":"D-002","updated_at":"2026-11-17T14:00:00Z","match_key":"browse available appointment slots","evidence":[{"evidence_id":"00000000-0000-4000-8000-000000000002","source_id":"BASELINE-001","kind":"requirement"}],"title":"Browse available appointment slots","description":"","status":"open","blocked_reason":null}');

insert into sentra_memory.evidence
    (evidence_id, project_id, source_type, source_id, kind, quote, start_offset, end_offset)
values ('00000000-0000-4000-8000-000000000003', 'maple-grove-demo', 'meeting', 'BASELINE-001',
        'requirement', 'Book an appointment', 68, 87);
insert into sentra_memory.deliverables (project_id, id, data)
values ('maple-grove-demo', 'D-003', '{"id":"D-003","updated_at":"2026-11-17T14:00:00Z","match_key":"book an appointment","evidence":[{"evidence_id":"00000000-0000-4000-8000-000000000003","source_id":"BASELINE-001","kind":"requirement"}],"title":"Book an appointment","description":"","status":"open","blocked_reason":null}');

insert into sentra_memory.evidence
    (evidence_id, project_id, source_type, source_id, kind, quote, start_offset, end_offset)
values ('00000000-0000-4000-8000-000000000004', 'maple-grove-demo', 'meeting', 'BASELINE-001',
        'requirement', 'Cancel an appointment', 88, 109);
insert into sentra_memory.deliverables (project_id, id, data)
values ('maple-grove-demo', 'D-004', '{"id":"D-004","updated_at":"2026-11-17T14:00:00Z","match_key":"cancel an appointment","evidence":[{"evidence_id":"00000000-0000-4000-8000-000000000004","source_id":"BASELINE-001","kind":"requirement"}],"title":"Cancel an appointment","description":"","status":"open","blocked_reason":null}');

insert into sentra_memory.evidence
    (evidence_id, project_id, source_type, source_id, kind, quote, start_offset, end_offset)
values ('00000000-0000-4000-8000-000000000005', 'maple-grove-demo', 'meeting', 'BASELINE-001',
        'requirement', 'SMS booking confirmations', 110, 135);
insert into sentra_memory.deliverables (project_id, id, data)
values ('maple-grove-demo', 'D-005', '{"id":"D-005","updated_at":"2026-11-17T14:00:00Z","match_key":"sms booking confirmations","evidence":[{"evidence_id":"00000000-0000-4000-8000-000000000005","source_id":"BASELINE-001","kind":"requirement"}],"title":"SMS booking confirmations","description":"","status":"open","blocked_reason":null}');

insert into sentra_memory.evidence
    (evidence_id, project_id, source_type, source_id, kind, quote, start_offset, end_offset)
values ('00000000-0000-4000-8000-000000000006', 'maple-grove-demo', 'meeting', 'BASELINE-001',
        'requirement', 'Staff admin dashboard', 136, 157);
insert into sentra_memory.deliverables (project_id, id, data)
values ('maple-grove-demo', 'D-006', '{"id":"D-006","updated_at":"2026-11-17T14:00:00Z","match_key":"staff admin dashboard","evidence":[{"evidence_id":"00000000-0000-4000-8000-000000000006","source_id":"BASELINE-001","kind":"requirement"}],"title":"Staff admin dashboard","description":"","status":"open","blocked_reason":null}');

insert into sentra_memory.evidence
    (evidence_id, project_id, source_type, source_id, kind, quote, start_offset, end_offset)
values ('00000000-0000-4000-8000-000000000007', 'maple-grove-demo', 'meeting', 'BASELINE-001',
        'requirement', 'Which SMS provider should be used?', 158, 192);
insert into sentra_memory.questions (project_id, id, data)
values ('maple-grove-demo', 'Q-001', '{"id":"Q-001","updated_at":"2026-11-17T14:00:00Z","match_key":"which sms provider should be used","evidence":[{"evidence_id":"00000000-0000-4000-8000-000000000007","source_id":"BASELINE-001","kind":"requirement"}],"question":"Which SMS provider should be used?","state":"open","requires_client_consent":true,"answer":null,"answered_source_id":null}');

insert into sentra_memory.evidence
    (evidence_id, project_id, source_type, source_id, kind, quote, start_offset, end_offset)
values ('00000000-0000-4000-8000-000000000008', 'maple-grove-demo', 'meeting', 'BASELINE-001',
        'requirement', 'What wording should SMS confirmation contain?', 193, 238);
insert into sentra_memory.questions (project_id, id, data)
values ('maple-grove-demo', 'Q-002', '{"id":"Q-002","updated_at":"2026-11-17T14:00:00Z","match_key":"what wording should sms confirmation contain","evidence":[{"evidence_id":"00000000-0000-4000-8000-000000000008","source_id":"BASELINE-001","kind":"requirement"}],"question":"What wording should SMS confirmation contain?","state":"open","requires_client_consent":true,"answer":null,"answered_source_id":null}');

insert into sentra_memory.evidence
    (evidence_id, project_id, source_type, source_id, kind, quote, start_offset, end_offset)
values ('00000000-0000-4000-8000-000000000009', 'maple-grove-demo', 'meeting', 'BASELINE-001',
        'decision', 'Use React, FastAPI and PostgreSQL for demo architecture.', 239, 295);
insert into sentra_memory.decisions (project_id, id, data)
values ('maple-grove-demo', 'DEC-001', '{"id":"DEC-001","updated_at":"2026-11-17T14:00:00Z","match_key":"demo architecture","evidence":[{"evidence_id":"00000000-0000-4000-8000-000000000009","source_id":"BASELINE-001","kind":"decision"}],"statement":"Use React, FastAPI and PostgreSQL for demo architecture.","state":"active","supersedes_id":null}');

insert into sentra_memory.events (project_id, revision, data)
values ('maple-grove-demo', 0, '{"action":"synthetic_baseline"}');
commit;
