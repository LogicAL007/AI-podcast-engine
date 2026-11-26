-- Cloned voices: a recording of someone's voice, kept with the consent its speaker gave, and which
CREATE TABLE IF NOT EXISTS voices (
  voice_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id          uuid NOT NULL REFERENCES users ON DELETE CASCADE,
  name              text NOT NULL,
  speaker           text NOT NULL,
  license           text NOT NULL,
  source            text NOT NULL CHECK (source IN ('recorded', 'uploaded')),
  consent           jsonb NOT NULL,
  object_key        text NOT NULL,
  size_bytes        integer NOT NULL,
  duration_seconds  real NOT NULL,
  sha256            text NOT NULL,
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS voices_owner_idx ON voices (owner_id, created_at DESC);

-- Which registered voice each host of a show speaks with: {"Alex": "<voice_id>"}. Hosts not
-- listed keep the voice backend's own voice.
ALTER TABLE shows ADD COLUMN IF NOT EXISTS host_voices jsonb NOT NULL DEFAULT '{}';
