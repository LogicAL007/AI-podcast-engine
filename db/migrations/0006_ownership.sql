-- Per-creator ownership. A show belongs to one user; everything else (episodes, sources, chunks,
-- segments, claims, stage runs, uploads) already belongs to a show, so ownership follows from it.
-- Idempotent, like 0003.

-- Nullable only for shows created before login existed: the first account to register (the
-- admin) claims them. The API never creates a show without an owner and never shows an unowned
-- one to anyone.
ALTER TABLE shows ADD COLUMN IF NOT EXISTS owner_id uuid REFERENCES users ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS shows_owner_idx ON shows (owner_id, created_at DESC);
