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
  scheduler/       periodic refresh of published shows (FR8)
  worker.py        `python -m podcast_engine.worker <stage>`
  pipeline.py      `python -m podcast_engine.pipeline`: every stage in one process (tests, host runs)
web/               React + Vite UI, served by nginx
db/init/           SQL run when the Postgres volume is first created
db/migrations/     idempotent SQL applied by the `db-migrate` service on every `up`
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
| db-migrate | `./db/migrations` (ro); one-shot: applies migrations, then exits |
| api | `uploads` → `/data/uploads`; `./config` (ro); runs uvicorn (`api` image target) |
| web | `./web/nginx.conf` (ro) |
| scheduler | `scheduler_state` → `/data/scheduler`; `./config` (ro) |
| ingest | `ingest_cache` → `/data/ingest`; `uploads` (ro); `./config` (ro) |
| index | `hf_cache` → `/home/app/.cache/huggingface`; `./config` (ro) |
| retrieve_plan | `hf_cache`; `./config` (ro); `./prompts` (ro) |
| script | `./config` (ro); `./prompts` (ro) |
| factcheck | `./config` (ro); `./prompts` (ro) |
| voice | `tts_cache` → `/data/tts_cache`; `audio_scratch` → `/data/audio`; `./config` (ro); `./assets` (ro) |
| assemble | `audio_scratch` → `/data/audio`; `./assets` (ro) |
| publish | `feed_staging` → `/data/feeds`; `./config` (ro) |
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

## Running an episode

The stages implement the flow validated in `notebooks/podcast_flow.ipynb`. A web page is split into
sections, and each section is a source with its own hash and anchor. Sections are chunked
(80 words, 40 overlap) and embedded into pgvector. Passages are ranked by topic, recency and
authority, one segment is planned per section, and a two-host script quotes or paraphrases cited
passages. The fact-check gate loops back to the script stage, then lines are voiced, mixed to
-16 LUFS and published as show notes and RSS.

```bash
curl -X POST localhost:8000/shows -H 'content-type: application/json' -d '{
  "topic": "What ClickHouse is and why it is fast for analytics",
  "sources": ["https://clickhouse.com/docs/get-started/about/intro"],
  "topic_keywords": "ClickHouse column-oriented database OLAP analytics queries rows columns storage",
  "attribution": "Source material: What is ClickHouse?, ClickHouse Documentation (CC BY-NC-SA 4.0).",
  "max_segments": 6, "tone": "casual", "expertise": "beginner", "target_minutes": 3}'
curl -X POST localhost:8000/shows/<show_id>/episodes       # 202; starts the pipeline
curl localhost:8000/episodes/<episode_id>                  # status and current stage
curl localhost:8000/episodes/<episode_id>/script           # claims, citations, verdicts
curl -o episode.wav localhost:8000/episodes/<episode_id>/audio.wav
curl localhost:8000/feeds/<show_id>/rss.xml
```

Posting another episode for the same show is a **refresh** (FR8). Only segments whose sections
changed are re-scripted and re-voiced. If nothing changed, the episode ends as `unchanged`. Set
`REFRESH_INTERVAL_HOURS` to have the scheduler do this on a timer.

| Setting (`.env`) | Default | |
|---|---|---|
| `LLM_ENABLED` | `false` | `false`: offline extractive writer and word-overlap judge, no key and no cost. `true`: `LLM_PROVIDER`/`LLM_MODEL` (Gemini `gemini-3.8-flash`, or `anthropic`) plan, write and judge, with the key in `secrets/llm_api_key.txt` |
| `EMBEDDING_MODEL` | `hashing` | Offline. A sentence-transformers id works if it has 384 dimensions (for example `BAAI/bge-small-en-v1.5`) |
| `TTS_BACKEND` | `placeholder` | `placeholder` (tones, for testing) or `gemini` (prebuilt voices, key in `secrets/tts_api_key.txt`, else the LLM key) in containers. `say` and `chatterbox` run on a host, see below |
| `MAX_REWRITES` | `2` | Gate loops before an episode is held as `needs_review` |
| `REFRESH_INTERVAL_HOURS` | `0` | Scheduler refresh period for published shows; `0` is off |

**Cloned voices (Chatterbox) run on the host.** Chatterbox needs torch and ideally a GPU (MPS on a
Mac), so it is not in the voice image. Stop the voice container and run the voice worker from
`.venv-cloning` against the stack. The dev overlay publishes the ports. `config/voices.yaml` holds
the consent record each cloned voice needs.

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d   # ports on localhost
docker compose stop voice
.venv-cloning/bin/pip install -e .     # once, after pulling
DATABASE_URL=postgresql+psycopg://podcast:<POSTGRES_PASSWORD>@localhost:5432/podcast \
REDIS_URL=redis://localhost:6379/0 S3_ENDPOINT_URL=http://localhost:9000 \
TTS_BACKEND=chatterbox CONFIG_DIR=$PWD/config ASSETS_DIR=$PWD/assets PROMPTS_DIR=$PWD/prompts \
WORKER_POOL=solo WORKER_CONCURRENCY=1 METRICS_PORT=9101 \
.venv-cloning/bin/python -m podcast_engine.worker voice
```

`python -m podcast_engine.pipeline --show <show_id>` runs every stage in one process with the same
settings, which is handy for one-off host runs.

## Status

Implemented: the API, all eight stages, the fact-check loop, incremental refresh and the
scheduler, tested end to end against Postgres with offline settings
([tests/integration/test_pipeline.py](tests/integration/test_pipeline.py)). Not built yet: RSS
feeds as a source type, PDF uploads (PyMuPDF), pages behind authentication, MP3 output, script
editing before voicing (the script is readable at `/episodes/{id}/script`), and authentication.
The Gemini and Claude paths are exercised only against fake SDKs in the notebook tests.

Before the first release: add a dependency lockfile (`uv lock` or `pip-compile`).
