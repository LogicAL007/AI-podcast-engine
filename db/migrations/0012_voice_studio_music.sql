-- Voice studio 2: host voice effects, type-to-speech clips and music.
ALTER TABLE shows ADD COLUMN IF NOT EXISTS host_effects jsonb NOT NULL DEFAULT '{}';
ALTER TABLE shows ADD COLUMN IF NOT EXISTS music jsonb NOT NULL DEFAULT '{}';

-- Type-to-speech: a line typed in the voice studio, voiced by the voice worker. The row is the job
-- and, once done, the clip (object_key).
CREATE TABLE IF NOT EXISTS speech_clips (
  clip_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id     uuid NOT NULL REFERENCES users ON DELETE CASCADE,
  voice        jsonb NOT NULL,
  text         text NOT NULL,
  delivery     text NOT NULL DEFAULT 'neutral',
  effects      jsonb NOT NULL DEFAULT '{}',
  status       text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'working', 'done', 'failed')),
  object_key   text,
  duration_s   real,
  error        text,
  created_at   timestamptz NOT NULL DEFAULT now(),
  finished_at  timestamptz
);
CREATE INDEX IF NOT EXISTS speech_clips_owner_idx ON speech_clips (owner_id, created_at DESC);

-- Music the owner uploaded, with their statement that they may use it. Built-in tracks are made in
-- code (podcast_engine.common.music) and have no row.
CREATE TABLE IF NOT EXISTS music_tracks (
  track_id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id             uuid NOT NULL REFERENCES users ON DELETE CASCADE,
  name                 text NOT NULL,
  role                 text NOT NULL CHECK (role IN ('bed', 'intro', 'outro', 'sting', 'any')),
  credit               text NOT NULL DEFAULT '',
  object_key           text NOT NULL,
  size_bytes           integer NOT NULL,
  duration_seconds     real NOT NULL,
  sha256               text NOT NULL,
  rights_confirmed_at  timestamptz NOT NULL,
  created_at           timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS music_tracks_owner_idx ON music_tracks (owner_id, created_at DESC);
