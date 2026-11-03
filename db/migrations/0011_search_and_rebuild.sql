-- Search results as a source (FR2), and refreshing an episode by hand (FR8). Idempotent, like 0003.
--
-- shows.search_queries: searches run each time an episode is made; their top results are read
-- like the show's own pages, so a refresh sees new results as changed sources.
-- episodes.rebuild: a refresh that regenerates every segment, not only those whose sources
-- changed, and runs even when no source changed.
ALTER TABLE shows ADD COLUMN IF NOT EXISTS search_queries jsonb NOT NULL DEFAULT '[]';
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS rebuild boolean NOT NULL DEFAULT false;
