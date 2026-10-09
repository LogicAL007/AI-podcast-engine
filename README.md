# AI Podcast Engine

Turns live, changing sources into a grounded, multi-voice podcast episode. Each episode is
assembled at generation time from current sources, with every factual claim tied to a cited
passage. See the PRD for goals, requirements (FR1–FR13) and the evaluation plan.

## Pipeline

```
ingest → index → retrieve_plan → script ⇄ factcheck → voice → assemble → publish
```

Every stage is its own worker container consuming its own Redis queue. Workers are stateless:
they pass only the episode id, and read and write state in Postgres (pgvector) and S3-compatible storage.
`factcheck` sends scripts with unsupported claims back to `script` until `MAX_REWRITES` is
spent, then holds the episode for human review.

## Layout

```
src/podcast_engine/
  common/          settings, logging, queue wiring, domain models, storage, stage runner
  stages/<stage>/  service.py (typed logic) + tasks.py (queue entrypoint), one per stage
  api/             routers/ controllers/ services/ models/ repositories/, one <resource>_<layer>.py each
  scheduler/       source watching and incremental regeneration (FR8)
  worker.py        `python -m podcast_engine.worker <stage>`
web/               React + Vite UI, served by nginx
db/init/           SQL run when the Postgres volume is first created
config/            show definitions, source reliability tiers, pronunciation lexicon
prompts/           versioned prompts (`<name>.v<N>.md`), logged per episode
assets/audio/      intro/outro/transition audio
evaluation/        RQ1–RQ3 study material and benchmarks (not containerised)
docs/              api.md (the API), observability.md (metrics and logs), notebook.md (the flow notebook)
notebooks/         podcast_flow.ipynb: the whole pipeline, runnable offline
monitoring/        Prometheus scrape configuration
docker/            stage.Dockerfile, the one recipe behind every Python image (api and worker targets)
tests/             unit/ (no services needed), integration/ (marked `integration`)
```

## Docker

`docker-compose.yml` builds one service per stage plus `api`, `web`, `scheduler`, Postgres,
Redis and RustFS (S3-compatible; MinIO no longer publishes images). Python images share `docker/stage.Dockerfile`; build args pick the extras and
system packages each stage needs (for example only `assemble` installs `ffmpeg`).

| Service | Volumes |
|---|---|
| postgres | `pgdata` → `/var/lib/postgresql/data`; `./db/init` → `/docker-entrypoint-initdb.d` (ro) |
| redis | `redisdata` → `/data` |
| s3 | `s3data` → `/data` |
| s3-init | none (one-shot: creates the bucket, then exits) |
| api | `uploads` → `/data/uploads`; `./config` (ro); runs uvicorn (`api` image target) |
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
| prometheus | `prometheus_data` → `/prometheus`; `./monitoring/prometheus.yml` (ro) |

Containers run as a non-root user with a read-only root filesystem, all capabilities dropped
and rotated JSON logs. API keys are Docker secrets read from `./secrets/*.txt`, never
environment variables.

```bash
make secrets        # creates .env and empty secrets/llm_api_key.txt, tts_api_key.txt
# put your keys in secrets/*.txt and set passwords in .env
make up             # full stack; UI :8080, API :8000, Prometheus :9090, S3 console :9001
make dev            # same, with ./src mounted for edits without rebuilding
```

## Development

```bash
make setup          # editable install + pre-commit hooks
make check          # ruff, strict mypy, unit tests (what CI runs)
make notebook-test  # runs notebooks/podcast_flow.ipynb offline and checks the flow
```

## Status

The API is implemented (shows, episodes, RSS feeds; see [docs/api.md](docs/api.md)). The
pipeline is wired end to end (queues, routing, retries, timing, config, schema, images), but the
stage bodies are not written yet: each stage's main function in `service.py` raises
`NotImplementedError` naming the requirement it covers, and the scheduler logs that change
detection is not implemented. Until the stages exist, an episode started through the API stays
`queued`. Small pure helpers that the
design depends on (content hashing, chunking, freshness scoring, fact-check routing, TTS cache
keys, loudness check, AI disclosure) are implemented and tested.

Before the first release: add a dependency lockfile (`uv lock` or `pip-compile`) and choose the
TTS provider (`TTS_PROVIDER`).
