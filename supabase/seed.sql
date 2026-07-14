-- ============================================================================
-- Seed teams.
--
-- Teams are no longer hand-seeded here. All teams are created live through
-- POST /admin/teams (Admin UI -> Teams tab), which:
--   - requires 2-4 member_emails (validated server-side)
--   - generates an access code in the form <team_name_slug>-<5 digit number>
--   - emails the access code to every listed member via Resend
--
-- This file is kept only so `psql -f seed.sql` after a fresh schema.sql apply
-- doesn't error on a missing file in older setup docs. It intentionally
-- inserts nothing.
-- ============================================================================

select 'No teams seeded here -- create teams via POST /admin/teams.' as note;
