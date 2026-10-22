-- Security event log, and MP3 audio. Idempotent, like 0003.

-- Who did what to an account and when: sign-ins, locks, resets, keys, account changes. Kept
-- after the user is deleted (user_id set null) so the trail survives; the email is never stored,
-- only its hash for failed sign-ins to unknown accounts.
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
