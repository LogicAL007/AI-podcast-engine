ALTER TABLE shows ADD COLUMN IF NOT EXISTS owner_id uuid REFERENCES users ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS shows_owner_idx ON shows (owner_id, created_at DESC);
