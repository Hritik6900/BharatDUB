-- A Live session can ask for the all-GPU engine ('gpu'); null = the hosted services, as before.
alter table live_sessions add column if not exists engine text;
