-- Core schema. Runs once, when the postgres volume is first created.
-- vector(384) matches BAAI/bge-small-en-v1.5; change both together (EMBEDDING_DIMENSIONS).

CREATE TABLE shows (
  show_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  topic        text NOT NULL,
  tone         text NOT NULL DEFAULT 'neutral',
  target_minutes integer NOT NULL DEFAULT 7 CHECK (target_minutes BETWEEN 1 AND 30),
  host_count   integer NOT NULL DEFAULT 2 CHECK (host_count BETWEEN 1 AND 4),
  language     text NOT NULL DEFAULT 'en',
  expertise    text NOT NULL DEFAULT 'intermediate',
  sources      jsonb NOT NULL DEFAULT '[]',
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE source_items (
  item_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  show_id      uuid NOT NULL REFERENCES shows ON DELETE CASCADE,
  url          text NOT NULL,
  title        text NOT NULL,
  published_at timestamptz,
  content_hash text NOT NULL,
  reliability  text NOT NULL DEFAULT 'unverified',
  fetched_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (show_id, url)
);

CREATE TABLE chunks (
  chunk_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  item_id      uuid NOT NULL REFERENCES source_items ON DELETE CASCADE,
  position     integer NOT NULL,
  text         text NOT NULL,
  embedding    vector(384) NOT NULL,
  UNIQUE (item_id, position)
);
CREATE INDEX chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);

CREATE TABLE episodes (
  episode_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  show_id        uuid NOT NULL REFERENCES shows ON DELETE CASCADE,
  status         text NOT NULL DEFAULT 'queued',
  rewrite_count  integer NOT NULL DEFAULT 0,
  audio_key      text,
  created_at     timestamptz NOT NULL DEFAULT now(),
  published_at   timestamptz
);

CREATE TABLE segments (
  segment_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  episode_id   uuid NOT NULL REFERENCES episodes ON DELETE CASCADE,
  position     integer NOT NULL,
  title        text NOT NULL,
  source_item_ids uuid[] NOT NULL,
  audio_key    text,
  UNIQUE (episode_id, position)
);

CREATE TABLE claims (
  claim_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  episode_id   uuid NOT NULL REFERENCES episodes ON DELETE CASCADE,
  segment_id   uuid REFERENCES segments ON DELETE SET NULL,
  text         text NOT NULL,
  chunk_ids    uuid[] NOT NULL DEFAULT '{}',
  supported    boolean
);

-- Transparency and reproducibility: one row per stage run with versions and seed.
CREATE TABLE stage_runs (
  run_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  episode_id      uuid NOT NULL REFERENCES episodes ON DELETE CASCADE,
  stage           text NOT NULL,
  model           text,
  prompt_version  text,
  seed            bigint,
  seconds         numeric,
  cost_usd        numeric,
  started_at      timestamptz NOT NULL DEFAULT now()
);
