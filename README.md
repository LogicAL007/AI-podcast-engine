# AI Podcast Engine

Turns live, changing sources into a grounded, multi-voice podcast episode. Each episode is
assembled at generation time from current sources, with every factual claim tied to a cited
passage. See the PRD for goals, requirements (FR1–FR13) and the evaluation plan.

## Pipeline

```
ingest → index → retrieve_plan → script ⇄ factcheck → voice → assemble → publish
```

Every stage is its own worker container consuming its own Redis queue. Workers are stateless:
they pass only the episode id, and read and write state in Postgres (pgvector) and MinIO.
`factcheck` sends scripts with unsupported claims back to `script` until `MAX_REWRITES` is
spent, then holds the episode for human review.

## Layout

```
src/podcast_engine/
  common/          settings, logging, queue wiring, domain models, storage, stage runner
  stages/<stage>/  service.py (typed logic) + tasks.py (queue entrypoint), one per stage
  api/             FastAPI app and routers (shows, episodes, feeds)
  scheduler/       source watching and incremental regeneration (FR8)
  worker.py        `python -m podcast_engine.worker <stage>`
web/               React + Vite UI, served by nginx
db/init/           SQL run when the Postgres volume is first created
config/            show definitions, source reliability tiers, pronunciation lexicon
prompts/           versioned prompts (`<name>.v<N>.md`), logged per episode
assets/audio/      intro/outro/transition audio
evaluation/        RQ1–RQ3 study material and benchmarks (not containerised)
docker/            stage.Dockerfile, the one recipe behind every Python image
tests/             unit/ (no services needed), integration/ (marked `integration`)
```

## Docker

`docker-compose.yml` builds one service per stage plus `api`, `web`, `scheduler`, Postgres,
Redis and MinIO. Python images share `docker/stage.Dockerfile`; build args pick the extras and
system packages each stage needs (for example only `assemble` installs `ffmpeg`).

| Service | Volumes |
|---|---|
| postgres | `pgdata` → `/var/lib/postgresql/data`; `./db/init` → `/docker-entrypoint-initdb.d` (ro) |
| redis | `redisdata` → `/data` |
| minio | `miniodata` → `/data` |
| api | `uploads` → `/data/uploads`; `./config` (ro) |
| web | `./web/nginx.conf` (ro) |
| scheduler | `scheduler_state` → `/data/scheduler`; `./config` (ro) |
| ingest | `ingest_cache` → `/data/ingest`; `uploads` (ro); `./config` (ro) |
| index | `hf_cache` → `/home/app/.cache/huggingface`; `./config` (ro) |
| retrieve_plan | `hf_cache`; `./config` (ro); `./prompts` (ro) |
| script | `./config` (ro); `./prompts` (ro) |
| factcheck | `./prompts` (ro) |
| voice | `tts_cache` → `/data/tts_cache`; `audio_scratch` → `/data/audio`; `./config` (ro) |
| assemble | `audio_scratch` → `/data/audio`; `./assets` (ro) |
| publish | `feed_staging` → `/data/feeds` |

Containers run as a non-root user with a read-only root filesystem, all capabilities dropped
and rotated JSON logs. API keys are Docker secrets read from `./secrets/*.txt`, never
environment variables.

```bash
make secrets        # creates .env and empty secrets/llm_api_key.txt, tts_api_key.txt
# put your keys in secrets/*.txt and set passwords in .env
make up             # full stack; UI on :8080, API on :8000, MinIO console on :9001
make dev            # same, with ./src mounted for edits without rebuilding
```

## Development

```bash
make setup          # editable install + pre-commit hooks
make check          # ruff, strict mypy, unit tests (what CI runs)
```

## Status

The scaffold is wired end to end (queues, routing, retries, timing, config, schema, images),
but the stage bodies are not written yet. Each stage's main function in `service.py` raises
`NotImplementedError` naming the requirement it covers, the API resource routes return 501, and
the scheduler logs that change detection is not implemented. Small pure helpers that the
design depends on (content hashing, chunking, freshness scoring, fact-check routing, TTS cache
keys, loudness check, AI disclosure) are implemented and tested.

Before the first release: add a dependency lockfile (`uv lock` or `pip-compile`), pin the
`minio` image tags, and choose the TTS provider (`TTS_PROVIDER`).
