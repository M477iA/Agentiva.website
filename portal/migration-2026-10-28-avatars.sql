-- ============================================================
-- Migration 2026-10-28 — "Personas": profile photos
-- Run in: Supabase dashboard (cyczjwnqrzxbngiqhzcj) → SQL Editor
-- Idempotent: safe to run more than once.
-- ============================================================

-- Public URL of the person's photo (with a ?v= cache-buster), NULL = initials.
-- Written only by api/team.py (service key) after it stores the file.
ALTER TABLE client_profiles ADD COLUMN IF NOT EXISTS avatar_url TEXT;

-- Public bucket: photos are shown to the owner and in the viewer by plain URL.
-- No storage policies needed — uploads go through api/team.py with the service key.
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('avatars', 'avatars', TRUE, 524288, ARRAY['image/jpeg'])
ON CONFLICT (id) DO NOTHING;
