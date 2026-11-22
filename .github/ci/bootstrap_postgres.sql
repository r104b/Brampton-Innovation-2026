-- Test-only roles matching the Supabase role names used by the migrations.
create role anon nologin;
create role authenticated nologin;
create role service_role nologin bypassrls;
