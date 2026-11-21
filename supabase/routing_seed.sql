-- Apply after 001, the original seed, and 002. Replace YOUR_TEAM with your team.
begin;
insert into sentra_memory.customers(customer_id,customer_name) values
 ('maple-grove','Fictional Maple Grove Dental'),('harbor-demo','Fictional Harbor Services');
update sentra_memory.projects set customer_id='maple-grove',
 allowed_senders='["jordan.lee@example.test"]',
 agent_purpose='Maintain the fictional clinic appointment assistant'
where project_id='maple-grove-demo';
insert into sentra_memory.projects(project_id,customer_id,project_name,project_summary,
 client_senders,allowed_senders,agent_purpose) values
 ('harbor-demo','harbor-demo','Fictional Harbor Intake','Synthetic marine service intake project',
 '["owner@harbor.example.test"]','["owner@harbor.example.test"]','Maintain the fictional harbor intake assistant');
insert into sentra_memory.repository_mappings(mapping_id,project_id,owner,repository_name,branch,context_path) values
 ('map-maple','maple-grove-demo','YOUR_TEAM','maple-grove-agent','main','context/CURRENT_STATE.md'),
 ('map-harbor','harbor-demo','YOUR_TEAM','harbor-agent','main','context/CURRENT_STATE.md');
commit;
