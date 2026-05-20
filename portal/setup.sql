-- ============================================================
-- Agentiva Client Portal — Supabase Schema
-- Run this in: Supabase dashboard → SQL Editor
-- ============================================================

-- ── TABLES ──────────────────────────────────────────────────

CREATE TABLE client_profiles (
  id        UUID        PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  nombre    TEXT        NOT NULL,
  empresa   TEXT,
  email     TEXT        NOT NULL UNIQUE,
  phone     TEXT,
  role      TEXT        NOT NULL DEFAULT 'client' CHECK (role IN ('client', 'admin')),
  notas     TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE services (
  id          UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
  client_id   UUID        NOT NULL REFERENCES client_profiles(id) ON DELETE CASCADE,
  nombre      TEXT        NOT NULL,
  descripcion TEXT,
  precio      NUMERIC(10,2),
  moneda      TEXT        NOT NULL DEFAULT 'USD' CHECK (moneda IN ('USD', 'ARS', 'EUR')),
  estado      TEXT        NOT NULL DEFAULT 'activo' CHECK (estado IN ('activo', 'pausado', 'cancelado')),
  fecha_inicio DATE,
  fecha_fin    DATE,
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE pagos (
  id                UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
  client_id         UUID        NOT NULL REFERENCES client_profiles(id) ON DELETE CASCADE,
  service_id        UUID        REFERENCES services(id) ON DELETE SET NULL,
  fecha_vencimiento DATE        NOT NULL,
  fecha_pago        DATE,
  monto             NUMERIC(10,2) NOT NULL,
  moneda            TEXT        NOT NULL DEFAULT 'USD' CHECK (moneda IN ('USD', 'ARS', 'EUR')),
  estado            TEXT        NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'pagado', 'vencido')),
  notas             TEXT,
  created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE agentiva_costs (
  id          UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id   UUID          REFERENCES client_profiles(id) ON DELETE SET NULL,
  category    TEXT          NOT NULL,
  description TEXT,
  amount_usd  NUMERIC(10,6) NOT NULL,
  date        DATE          NOT NULL DEFAULT CURRENT_DATE,
  created_at  TIMESTAMPTZ   DEFAULT NOW()
);

-- ── ROW-LEVEL SECURITY ───────────────────────────────────────

ALTER TABLE client_profiles  ENABLE ROW LEVEL SECURITY;
ALTER TABLE services         ENABLE ROW LEVEL SECURITY;
ALTER TABLE pagos            ENABLE ROW LEVEL SECURITY;
ALTER TABLE agentiva_costs   ENABLE ROW LEVEL SECURITY;

-- Helper function: returns current user's role without triggering RLS recursion
CREATE OR REPLACE FUNCTION get_my_role()
RETURNS TEXT LANGUAGE sql SECURITY DEFINER STABLE AS $$
  SELECT role FROM client_profiles WHERE id = auth.uid();
$$;

-- client_profiles
CREATE POLICY "read_own_or_admin" ON client_profiles
  FOR SELECT USING (auth.uid() = id OR get_my_role() = 'admin');

CREATE POLICY "insert_own" ON client_profiles
  FOR INSERT WITH CHECK (auth.uid() = id);

CREATE POLICY "update_own_or_admin" ON client_profiles
  FOR UPDATE USING (auth.uid() = id OR get_my_role() = 'admin');

CREATE POLICY "admin_delete" ON client_profiles
  FOR DELETE USING (get_my_role() = 'admin');

-- services
CREATE POLICY "read_own_or_admin_services" ON services
  FOR SELECT USING (client_id = auth.uid() OR get_my_role() = 'admin');

CREATE POLICY "admin_write_services" ON services
  FOR ALL USING (get_my_role() = 'admin');

-- pagos
CREATE POLICY "read_own_or_admin_pagos" ON pagos
  FOR SELECT USING (client_id = auth.uid() OR get_my_role() = 'admin');

CREATE POLICY "admin_write_pagos" ON pagos
  FOR ALL USING (get_my_role() = 'admin');

-- agentiva_costs (admin-only)
CREATE POLICY "admin_only_costs" ON agentiva_costs
  FOR ALL USING (get_my_role() = 'admin');

-- ── SETUP STEPS ─────────────────────────────────────────────
--
-- 1. Run this SQL in Supabase SQL Editor
--
-- 2. Go to Authentication → Users → "Invite user"
--    Create your own admin account with digital@prolianxe.com
--
-- 3. After creating your account, run this to make yourself admin:
--    UPDATE client_profiles SET role = 'admin' WHERE email = 'digital@prolianxe.com';
--
--    (You need to sign in once first so the profile row is created)
--
-- 4. To add a client manually:
--    a. Go to Authentication → Users → Invite user (enter client email)
--    b. Client sets password via the invite email
--    c. Their client_profiles row is created on first login automatically
--    d. Then in SQL Editor, add their services:
--
--       INSERT INTO services (client_id, nombre, descripcion, precio, moneda, fecha_inicio)
--       VALUES (
--         (SELECT id FROM client_profiles WHERE email = 'client@email.com'),
--         'Bot WhatsApp', 'Bot de atención al cliente por WhatsApp', 100, 'USD', '2025-01-01'
--       );
--
--    e. Add their recurring payments:
--
--       INSERT INTO pagos (client_id, service_id, fecha_vencimiento, monto, moneda)
--       VALUES (
--         (SELECT id FROM client_profiles WHERE email = 'client@email.com'),
--         (SELECT id FROM services WHERE nombre = 'Bot WhatsApp' LIMIT 1),
--         '2026-06-01', 100, 'USD'
--       );
--
-- ============================================================
