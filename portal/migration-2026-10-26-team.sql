-- ============================================================
-- Migration 2026-10-26 — "Mi Equipo": team members per client
-- Run in: Supabase dashboard (cyczjwnqrzxbngiqhzcj) → SQL Editor
-- Idempotent: safe to run more than once.
-- ============================================================

-- ── 1. client_profiles: members ─────────────────────────────
-- A member is a login that belongs to a client (owner_id). Members are
-- created by api/team.py (service key) with a synthetic email
-- <username>@team.agentiva.com.ar, so they log in with just the username.

ALTER TABLE client_profiles DROP CONSTRAINT IF EXISTS client_profiles_role_check;
ALTER TABLE client_profiles ADD CONSTRAINT client_profiles_role_check
  CHECK (role IN ('client', 'admin', 'member'));

ALTER TABLE client_profiles ADD COLUMN IF NOT EXISTS owner_id UUID REFERENCES client_profiles(id) ON DELETE CASCADE;
ALTER TABLE client_profiles ADD COLUMN IF NOT EXISTS username TEXT UNIQUE;
ALTER TABLE client_profiles ADD COLUMN IF NOT EXISTS activo   BOOLEAN NOT NULL DEFAULT TRUE;
CREATE INDEX IF NOT EXISTS client_profiles_owner_idx ON client_profiles(owner_id);

-- Owners can see their own members (list in "Mi Equipo")
DROP POLICY IF EXISTS "owner_reads_members" ON client_profiles;
CREATE POLICY "owner_reads_members" ON client_profiles
  FOR SELECT USING (owner_id = auth.uid());

-- Guard: only admin / service role may set role, owner_id, username or activo.
-- Closes a pre-existing hole: "insert_own" / "update_own_or_admin" let any
-- signed-in user write role = 'admin' on their own row.
-- SECURITY INVOKER on purpose, so current_user is the PostgREST role.
CREATE OR REPLACE FUNCTION protect_profile_fields()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  IF current_user NOT IN ('authenticated', 'anon') OR get_my_role() = 'admin' THEN
    RETURN NEW;
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.role <> 'client' OR NEW.owner_id IS NOT NULL OR NEW.username IS NOT NULL THEN
      RAISE EXCEPTION 'Not allowed to set role/owner on insert';
    END IF;
  ELSIF NEW.role     IS DISTINCT FROM OLD.role
     OR NEW.owner_id IS DISTINCT FROM OLD.owner_id
     OR NEW.username IS DISTINCT FROM OLD.username
     OR NEW.activo   IS DISTINCT FROM OLD.activo THEN
    RAISE EXCEPTION 'Not allowed to change role/owner/username/activo';
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS protect_profile_fields ON client_profiles;
CREATE TRIGGER protect_profile_fields
  BEFORE INSERT OR UPDATE ON client_profiles
  FOR EACH ROW EXECUTE FUNCTION protect_profile_fields();

-- Helper: is this member mine? (SECURITY DEFINER avoids RLS recursion)
CREATE OR REPLACE FUNCTION is_my_member(mid UUID)
RETURNS BOOLEAN LANGUAGE sql SECURITY DEFINER STABLE SET search_path = public AS $$
  SELECT EXISTS (SELECT 1 FROM client_profiles WHERE id = mid AND owner_id = auth.uid());
$$;

-- ── 2. team_member_filters ──────────────────────────────────
-- Generic visibility rules. No rows = member sees nothing.
--   ('handoff_reason', 'urgency')            reason the bot paused the chat
--   ('classification', 'needs_attention')    successful | needs_attention | unsuccessful | other
--   ('scope', 'paused_only')                 only chats currently paused
-- New filter types (topics, ...) need no schema change.

CREATE TABLE IF NOT EXISTS team_member_filters (
  member_id   UUID        NOT NULL REFERENCES client_profiles(id) ON DELETE CASCADE,
  filter_type TEXT        NOT NULL,
  value       TEXT        NOT NULL,
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (member_id, filter_type, value)
);
ALTER TABLE team_member_filters ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "filters_owner_or_admin" ON team_member_filters;
CREATE POLICY "filters_owner_or_admin" ON team_member_filters
  FOR ALL USING (is_my_member(member_id) OR get_my_role() = 'admin')
  WITH CHECK (is_my_member(member_id) OR get_my_role() = 'admin');

DROP POLICY IF EXISTS "filters_member_reads_own" ON team_member_filters;
CREATE POLICY "filters_member_reads_own" ON team_member_filters
  FOR SELECT USING (member_id = auth.uid());

-- ── 3. team_sessions ────────────────────────────────────────
-- Written only by the bot server (service key) from viewer heartbeats.

CREATE TABLE IF NOT EXISTS team_sessions (
  id             UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
  member_id      UUID        NOT NULL REFERENCES client_profiles(id) ON DELETE CASCADE,
  owner_id       UUID        NOT NULL REFERENCES client_profiles(id) ON DELETE CASCADE,
  started_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_seen_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  active_seconds INTEGER     NOT NULL DEFAULT 0,
  ended_at       TIMESTAMPTZ,
  end_reason     TEXT        CHECK (end_reason IN ('logout', 'idle'))
);
CREATE INDEX IF NOT EXISTS team_sessions_member_idx ON team_sessions(member_id, started_at DESC);
CREATE INDEX IF NOT EXISTS team_sessions_owner_idx  ON team_sessions(owner_id, started_at DESC);
ALTER TABLE team_sessions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "sessions_read" ON team_sessions;
CREATE POLICY "sessions_read" ON team_sessions
  FOR SELECT USING (owner_id = auth.uid() OR member_id = auth.uid() OR get_my_role() = 'admin');

-- ── 4. Member → viewer URL ──────────────────────────────────
-- Returns the owner's bot viewer URL WITHOUT its query string, so the legacy
-- static ?token= never reaches a member (they authenticate with their JWT).

CREATE OR REPLACE FUNCTION get_my_viewer_url()
RETURNS TEXT LANGUAGE sql SECURITY DEFINER STABLE SET search_path = public AS $$
  SELECT split_part(s.viewer_url, '?', 1)
  FROM client_profiles m
  JOIN services s ON s.client_id = m.owner_id
  WHERE m.id = auth.uid() AND m.role = 'member' AND m.activo
    AND s.viewer_url IS NOT NULL AND s.estado = 'activo'
  ORDER BY s.created_at
  LIMIT 1;
$$;

-- ── 5. Grants ───────────────────────────────────────────────
GRANT ALL ON public.team_member_filters, public.team_sessions TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.team_member_filters TO authenticated;
GRANT SELECT ON public.team_sessions TO authenticated;
GRANT EXECUTE ON FUNCTION get_my_viewer_url(), is_my_member(UUID) TO authenticated;
