alter table public.user_settings
  add column if not exists ftp_w integer not null default 0,
  add column if not exists ftp_updated_at timestamptz,
  add column if not exists ftp_method text not null default '',
  add column if not exists ftp_test_history jsonb not null default '[]'::jsonb;
