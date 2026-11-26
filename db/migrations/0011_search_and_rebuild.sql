-- Search results as a source (FR2), and refreshing an episode by hand (FR8).
ALTER TABLE shows ADD COLUMN IF NOT EXISTS search_queries jsonb NOT NULL DEFAULT '[]';
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS rebuild boolean NOT NULL DEFAULT false;
