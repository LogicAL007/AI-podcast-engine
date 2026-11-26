-- Pause every episode of a show after the fact-check, until a person approves it.
ALTER TABLE shows ADD COLUMN IF NOT EXISTS review_before_voice boolean NOT NULL DEFAULT false;

-- When a reviewer released the episode to voicing (cleared again when the script is edited).
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS approved_at timestamptz;
-- Paging and filtering by status across shows (the review queue).
CREATE INDEX IF NOT EXISTS episodes_status_idx ON episodes (status, created_at DESC);

-- Files a creator uploads as sources (PDFs). The bytes live in object storage at object_key.
CREATE TABLE IF NOT EXISTS uploads (
  upload_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  show_id      uuid NOT NULL REFERENCES shows ON DELETE CASCADE,
  filename     text NOT NULL,
  content_type text NOT NULL,
  size_bytes   bigint NOT NULL,
  object_key   text NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS uploads_show_idx ON uploads (show_id, created_at DESC);
