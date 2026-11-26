-- Security event log, and MP3 audio.
CREATE TABLE IF NOT EXISTS security_events (
  event_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid REFERENCES users ON DELETE SET NULL,
  event       text NOT NULL,
  address     text NOT NULL DEFAULT '',
  detail      jsonb NOT NULL DEFAULT '{}',
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS security_events_user_idx ON security_events (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS security_events_time_idx ON security_events (created_at DESC);

-- The episode as MP3 (what podcast apps and browsers expect); the WAV master stays in audio_key.
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS audio_mp3_key text;
