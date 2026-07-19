-- ============================================================================
-- Nepali Bias Data Collection — Supabase schema
-- Run this whole file once in the Supabase SQL editor (Project → SQL → New query).
-- Safe to re-run: drops and recreates policies, functions, and views.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------
create table if not exists teams (
  team_id        text primary key,
  team_name      text not null,
  access_code    text not null unique,
  member_emails  text[] not null default '{}',
  created_at     timestamptz not null default now(),
  constraint teams_member_emails_count check (
    array_length(member_emails, 1) between 2 and 4
  )
);

-- ---------------------------------------------------------------------------
-- Migration: member_emails replaces the old single contact_email column.
-- Safe to re-run. If contact_email still exists from an earlier deploy,
-- backfill it into member_emails as a single-entry array before dropping it,
-- so no data is silently lost on upgrade.
-- ---------------------------------------------------------------------------
alter table teams add column if not exists member_emails text[] not null default '{}';

do $$
begin
  if exists (
    select 1 from information_schema.columns
    where table_name = 'teams' and column_name = 'contact_email'
  ) then
    update teams
    set member_emails = array[contact_email]
    where contact_email is not null
      and (member_emails is null or array_length(member_emails, 1) is null);

    alter table teams drop column contact_email;
  end if;
end $$;

-- Constraint is added after backfill so pre-existing single-email rows from
-- the old contact_email column don't fail the 2-4 check on upgrade -- those
-- teams should be topped up to 2+ emails manually via /admin/teams.
alter table teams drop constraint if exists teams_member_emails_count;
alter table teams add constraint teams_member_emails_count
  check (array_length(member_emails, 1) between 2 and 4) not valid;

create table if not exists submissions (
  id              uuid primary key default gen_random_uuid(),
  team_id         text not null references teams(team_id) on delete restrict,
  text            text not null check (char_length(trim(text)) > 0),
  gender          int  not null default 0 check (gender in (0, 1)),
  religional      int  not null default 0 check (religional in (0, 1)),
  caste           int  not null default 0 check (caste in (0, 1)),
  religion        int  not null default 0 check (religion in (0, 1)),
  appearence      int  not null default 0 check (appearence in (0, 1)),
  socialstatus    int  not null default 0 check (socialstatus in (0, 1)),
  amiguity        int  not null default 0 check (amiguity in (0, 1)),
  political       int  not null default 0 check (political in (0, 1)),
  "Age"           int  not null default 0 check ("Age" in (0, 1)),
  "Disablity"     int  not null default 0 check ("Disablity" in (0, 1)),
  source_platform text,
  comment         text,
  submitted_at    timestamptz not null default now(),
  flag_duplicate  boolean not null default false,
  flag_pii        boolean not null default false,
  judge_reviewed  boolean not null default false,
  client_submission_id uuid
);

alter table submissions add column if not exists client_submission_id uuid;

-- Migration for deployments created before this column was repurposed:
-- source_date (an optional date picker) is replaced by comment (free text
-- explaining WHY the participant marked the sentence biased/non-biased).
-- Safe to run on a fresh DB too -- the rename is a no-op if source_date
-- never existed, and the create table above already names the column
-- "comment" directly for new installs.
do $$
begin
  if exists (
    select 1 from information_schema.columns
    where table_name = 'submissions' and column_name = 'source_date'
  ) and not exists (
    select 1 from information_schema.columns
    where table_name = 'submissions' and column_name = 'comment'
  ) then
    alter table submissions rename column source_date to comment;
  end if;
end $$;

-- Lets a retried /submit (e.g. from the frontend's offline outbox queue,
-- after a request whose response was lost to a network blip) be recognized
-- as "already saved" instead of inserted twice. Scoped per team_id so two
-- different teams' client-generated UUIDs can never collide.
create unique index if not exists submissions_team_client_id_idx
  on submissions(team_id, client_submission_id)
  where client_submission_id is not null;

-- ---------------------------------------------------------------------------
-- Indexes (performance for live queries, leaderboard, admin filters)
-- ---------------------------------------------------------------------------
create index if not exists submissions_team_idx
  on submissions(team_id);

create index if not exists submissions_time_idx
  on submissions(submitted_at desc);

create index if not exists submissions_team_time_idx
  on submissions(team_id, submitted_at desc);

create index if not exists submissions_flag_duplicate_idx
  on submissions(flag_duplicate)
  where flag_duplicate = true;

create index if not exists submissions_flag_pii_idx
  on submissions(flag_pii)
  where flag_pii = true;

create index if not exists submissions_judge_reviewed_idx
  on submissions(judge_reviewed)
  where judge_reviewed = false;

create index if not exists submissions_gender_idx
  on submissions(team_id, gender) where gender = 1;

create index if not exists submissions_caste_idx
  on submissions(team_id, caste) where caste = 1;

create index if not exists submissions_religional_idx
  on submissions(team_id, religional) where religional = 1;

create index if not exists submissions_religion_idx
  on submissions(team_id, religion) where religion = 1;

create index if not exists submissions_appearence_idx
  on submissions(team_id, appearence) where appearence = 1;

create index if not exists submissions_socialstatus_idx
  on submissions(team_id, socialstatus) where socialstatus = 1;

create index if not exists submissions_amiguity_idx
  on submissions(team_id, amiguity) where amiguity = 1;

create index if not exists submissions_political_idx
  on submissions(team_id, political) where political = 1;

create index if not exists submissions_age_idx
  on submissions(team_id, "Age") where "Age" = 1;

create index if not exists submissions_disablity_idx
  on submissions(team_id, "Disablity") where "Disablity" = 1;

create index if not exists teams_access_code_idx
  on teams(access_code);

-- ---------------------------------------------------------------------------
-- One-time cleanup: remove the static seed teams (team_01..team_05, team_dev)
-- and any submissions attributed to them. All teams are now created live
-- through POST /admin/teams; nothing should be hand-seeded anymore.
-- Safe to re-run -- matches by team_id, so it's a no-op once these are gone.
-- ---------------------------------------------------------------------------
delete from submissions
where team_id in ('team_01', 'team_02', 'team_03', 'team_04', 'team_05', 'team_dev');

delete from teams
where team_id in ('team_01', 'team_02', 'team_03', 'team_04', 'team_05', 'team_dev');

-- ---------------------------------------------------------------------------
-- Admins — multiple named organizer accounts, replacing the single shared
-- ADMIN_PASSWORD env var. password_hash is a bcrypt hash generated in
-- Python (backend/services/admin_service.py); Postgres never sees or
-- compares a plaintext password. Looked up by email via a service-role-only
-- RPC (verify_admin_email below) that returns the hash for the backend to
-- check with bcrypt -- the comparison itself happens in application code,
-- not in SQL, same reasoning as everywhere else in this schema: secrets
-- never leave service-role-only access, and hashing/verification logic
-- lives in one place (Python) instead of being duplicated in SQL.
-- ---------------------------------------------------------------------------
create table if not exists admins (
  admin_id       text primary key default ('admin_' || substr(gen_random_uuid()::text, 1, 8)),
  admin_name     text not null,
  email          text not null unique,
  password_hash  text not null,
  created_at     timestamptz not null default now()
);

create index if not exists admins_email_idx on admins(lower(email));

alter table admins enable row level security;
-- No anon policies -- only the backend's service role key can read/write
-- this table, same as teams/judges/submissions.

create or replace function verify_admin_email(admin_email text)
returns table (admin_id text, admin_name text, password_hash text)
language sql
security definer
set search_path = public
as $$
  select a.admin_id, a.admin_name, a.password_hash
  from admins a
  where lower(a.email) = lower(admin_email)
  limit 1;
$$;

revoke execute on function verify_admin_email(text) from anon;

-- ---------------------------------------------------------------------------
-- Judging — post-event only. A small pool of judges (separate login from
-- teams/admin) label a random sample blind (no original labels shown), so
-- organizers can compare judge labels vs. participant labels as a quality
-- check. Deliberately simple: one sample "round" at a time via
-- submissions.sampled_for_judging, not a full batch-history table, since
-- this runs once (or a couple of times) after the event closes.
-- ---------------------------------------------------------------------------
create table if not exists judges (
  judge_id     text primary key default ('judge_' || substr(gen_random_uuid()::text, 1, 8)),
  judge_name   text not null,
  access_code  text not null unique,
  created_at   timestamptz not null default now()
);

alter table submissions add column if not exists sampled_for_judging boolean not null default false;
alter table submissions add column if not exists sampled_at timestamptz;

create index if not exists submissions_sampled_idx
  on submissions(sampled_for_judging) where sampled_for_judging = true;

-- One label set per (submission, judge) -- a judge can revise their own
-- label (upsert), but can't create duplicate rows for the same item.
create table if not exists judge_labels (
  id            uuid primary key default gen_random_uuid(),
  submission_id uuid not null references submissions(id) on delete cascade,
  judge_id      text not null references judges(judge_id) on delete cascade,
  gender        int not null default 0 check (gender in (0, 1)),
  religional    int not null default 0 check (religional in (0, 1)),
  caste         int not null default 0 check (caste in (0, 1)),
  religion      int not null default 0 check (religion in (0, 1)),
  appearence    int not null default 0 check (appearence in (0, 1)),
  socialstatus  int not null default 0 check (socialstatus in (0, 1)),
  amiguity      int not null default 0 check (amiguity in (0, 1)),
  political     int not null default 0 check (political in (0, 1)),
  "Age"         int not null default 0 check ("Age" in (0, 1)),
  "Disablity"   int not null default 0 check ("Disablity" in (0, 1)),
  submitted_at  timestamptz not null default now(),
  unique (submission_id, judge_id)
);

create index if not exists judge_labels_submission_idx
  on judge_labels(submission_id);

create index if not exists judges_access_code_idx
  on judges(access_code);

alter table judges       enable row level security;
alter table judge_labels enable row level security;
-- No anon policies -- same pattern as teams/submissions: only the backend's
-- service role key can read or write these tables.

create or replace function verify_judge_code(code text)
returns table (judge_id text, judge_name text)
language sql
security definer
set search_path = public
as $$
  select j.judge_id, j.judge_name
  from judges j
  where j.access_code = code
  limit 1;
$$;

revoke execute on function verify_judge_code(text) from anon;

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
-- SECURITY CHANGE: the frontend no longer talks to Supabase directly with the
-- anon key for reads/writes on submissions or teams. Every insert/select/update
-- now goes through the FastAPI backend (routers/submission.py, routers/admin.py)
-- using the service role key, which bypasses RLS and is never exposed to the
-- browser. That backend derives team_id from a signed session token instead of
-- trusting whatever the client sends, and only /admin/* routes (which require
-- an admin session token checked server-side) can read the full table or the
-- leaderboard. Previously, anon had "using (true)" select/insert/update
-- policies on submissions, which meant any browser holding the public anon key
-- could insert rows under any team_id, read every team's data, or tamper with
-- any row's judge_reviewed/flag_* columns directly via the Supabase REST API.
--
-- RLS stays enabled with NO anon policies at all, as defense in depth: even if
-- the anon key leaks, or a future change reintroduces a direct Supabase call
-- from the browser, anon can no longer read or write this table.
alter table submissions enable row level security;
alter table teams       enable row level security;

-- No anon policies on submissions or teams. Only the service_role key
-- (held only by the backend) can read or write these tables now.
drop policy if exists "anon insert submissions" on submissions;
drop policy if exists "anon select submissions" on submissions;
drop policy if exists "anon update submissions" on submissions;

-- ---------------------------------------------------------------------------
-- teams_public view — no longer needed by the frontend (login and the
-- leaderboard both go through the backend now), dropped along with its grant.
-- ---------------------------------------------------------------------------
drop view if exists teams_public;

-- ---------------------------------------------------------------------------
-- Login RPC — verify access code AND that the given email belongs to the
-- team (case-insensitive match against member_emails), without exposing the
-- access_code column. Requiring both means an access code alone (which
-- could be shared/leaked more easily) isn't enough to sign in as a team.
-- Called only by the backend (service role), so the anon EXECUTE grant is
-- revoked; the backend bypasses RLS/grants anyway via the service role key.
--
-- Drops the old single-argument version explicitly -- "create or replace"
-- doesn't touch it, since a different argument list is a different
-- overload in Postgres, not a replacement.
-- ---------------------------------------------------------------------------
drop function if exists verify_access_code(text);

create or replace function verify_access_code(code text, member_email text)
returns table (team_id text, team_name text)
language sql
security definer
set search_path = public
as $$
  select t.team_id, t.team_name
  from teams t
  where t.access_code = code
    and exists (
      select 1 from unnest(t.member_emails) as e
      where lower(e) = lower(member_email)
    )
  limit 1;
$$;

revoke execute on function verify_access_code(text, text) from anon;

-- ---------------------------------------------------------------------------
-- Helper: team submission count (kept for SQL-editor/manual use; the app now
-- gets this from GET /my-count on the backend instead).
-- ---------------------------------------------------------------------------
create or replace function team_submission_count(p_team_id text)
returns bigint
language sql
security definer
set search_path = public
stable
as $$
  select count(*)::bigint from submissions where team_id = p_team_id;
$$;

revoke execute on function team_submission_count(text) from anon;

-- ---------------------------------------------------------------------------
-- Realtime — subscribe to new inserts on dashboards
-- ---------------------------------------------------------------------------
do $$
begin
  begin
    alter publication supabase_realtime add table submissions;
  exception
    when duplicate_object then null;
    when undefined_object then null;
  end;
end $$;
