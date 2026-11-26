-- State the pipeline workers share (the notebook kept it in memory). Idempotent: safe on a fresh
-- database and on an existing volume, and recorded in schema_migrations by podcast_engine.common.migrate.

ALTER TABLE shows ADD COLUMN IF NOT EXISTS topic_keywords text NOT NULL DEFAULT '';
ALTER TABLE shows ADD COLUMN IF NOT EXISTS attribution text NOT NULL DEFAULT '';
ALTER TABLE shows ADD COLUMN IF NOT EXISTS max_segments integer NOT NULL DEFAULT 6;
ALTER TABLE shows ADD COLUMN IF NOT EXISTS ranking_profile text NOT NULL DEFAULT 'explainer';
DO $$ BEGIN
  ALTER TABLE shows ADD CONSTRAINT shows_max_segments_range CHECK (max_segments BETWEEN 1 AND 12);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- The section text itself, so later stages (and change detection) can read it.
ALTER TABLE source_items ADD COLUMN IF NOT EXISTS text text NOT NULL DEFAULT '';
ALTER TABLE source_items ADD COLUMN IF NOT EXISTS position integer NOT NULL DEFAULT 0;  -- order on the page

-- Episode progress and the artefacts each stage hands to the next.
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS revision integer NOT NULL DEFAULT 1;
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS stage text;               -- the stage running or last run
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS error text;               -- why it failed or was held
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS changed_item_ids uuid[];  -- set by ingest; NULL = all
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS script jsonb;             -- {position: [lines]}
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS fact_check jsonb;         -- latest gate report and history
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS voice_lines jsonb;        -- spoken lines and their audio keys
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS assembly jsonb;           -- chapters and audio checks
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS notes_key text;
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS manifest jsonb;           -- models, prompts, voices, seed

-- Which passages a segment draws on, and whether it must be (re)written.
ALTER TABLE segments ADD COLUMN IF NOT EXISTS chunk_ids uuid[] NOT NULL DEFAULT '{}';
ALTER TABLE segments ADD COLUMN IF NOT EXISTS needs_script boolean NOT NULL DEFAULT true;

-- Why the gate accepted or rejected a claim.
ALTER TABLE claims ADD COLUMN IF NOT EXISTS reason text;
ALTER TABLE claims ADD COLUMN IF NOT EXISTS position integer;  -- the segment it belongs to

CREATE INDEX IF NOT EXISTS episodes_show_idx ON episodes (show_id, created_at DESC);
CREATE INDEX IF NOT EXISTS claims_episode_idx ON claims (episode_id);
