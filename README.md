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
docs/              api.md (the API), erd.md (the data model), observability.md (metrics and logs), notebook.md
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

## Login and secrets

The API needs a login (see [docs/api.md](docs/api.md)). Application secrets live in HashiCorp
Vault, which runs in the stack over HTTPS (`vault`, UI on https://localhost:8200). Its
certificate comes from the stack's own CA, made by the one-shot `vault-certs` service and renewed
before it expires. Trust `secrets/vault-ca.pem` (for example `curl --cacert secrets/vault-ca.pem`),
and keep `secrets/vault-ca-key.pem` private. Password-reset email goes to Mailpit, a local inbox at
http://localhost:8025. Set `SMTP_HOST` and the rest to deliver real mail. At every `up`, the one-shot
`vault-init` service unseals Vault and issues the services a read-only token. On the first run it
also initialises Vault and generates the login-token key. The unseal key and root token are kept in
`secrets/vault-init.json`, which is git-ignored. Back it up: without it, Vault's data cannot be
read. Postgres and S3 passwords stay in `.env`, because those containers need them to start.

```bash
# store the Gemini (or Claude) key in Vault; the file only seeds it, Vault is the source after
docker compose run --rm -T vault-init set llm_api_key < secrets/llm_api_key.txt
docker compose restart retrieve_plan script factcheck   # services read secrets at start

# the first account becomes the admin; then log in for a six-month token
curl -X POST localhost:8000/auth/register -H 'content-type: application/json' \
  -d '{"email": "you@example.org", "password": "a long passphrase of your own"}'
TOKEN=$(curl -s -X POST localhost:8000/auth/login -H 'content-type: application/json' \
  -d '{"email": "you@example.org", "password": "a long passphrase of your own"}' | jq -r .access_token)
curl -H "Authorization: Bearer $TOKEN" localhost:8000/shows
```

In `/docs`, use **Authorize** and paste the token. `POST /auth/api-keys` creates a key for scripts.
It also lasts six months.

## Running an episode

The stages implement the flow validated in `notebooks/podcast_flow.ipynb`. A web page is split into
sections, and each section is a source with its own hash and anchor. Sections are chunked
(80 words, 40 overlap) and embedded into pgvector. Passages are ranked by topic, recency and
authority, one segment is planned per section, and a two-host script quotes or paraphrases cited
passages. The fact-check gate loops back to the script stage, then lines are voiced, mixed to
-16 LUFS and published as show notes and RSS.

```bash
curl localhost:8000/home                                   # every endpoint, auth and health
curl -X POST localhost:8000/shows -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' -d '{
  "topic": "What ClickHouse is and why it is fast for analytics",
  "sources": ["https://clickhouse.com/docs/get-started/about/intro"],
  "topic_keywords": "ClickHouse column-oriented database OLAP analytics queries rows columns storage",
  "attribution": "Source material: What is ClickHouse?, ClickHouse Documentation (CC BY-NC-SA 4.0).",
  "max_segments": 6, "tone": "casual", "expertise": "beginner", "target_minutes": 3}'
curl -X POST -H "Authorization: Bearer $TOKEN" localhost:8000/shows/<show_id>/episodes       # 202; starts the pipeline
curl -H "Authorization: Bearer $TOKEN" localhost:8000/episodes/<episode_id>                  # status and current stage
curl -H "Authorization: Bearer $TOKEN" localhost:8000/episodes/<episode_id>/script           # claims, citations, verdicts
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
scheduler; web pages, RSS/Atom feeds and uploaded PDFs as sources; review and editing before
voicing (`review_before_voice`, the review queue at `/episodes?status=needs_review`); retry,
cancel and delete; paginated lists. Tested end to end against Postgres with offline settings
([tests/integration/](tests/integration/)). Not built yet: search results as a source, pages
behind authentication, and MP3 output. Each user sees only their own shows
([docs/erd.md](docs/erd.md)).
The Gemini and Claude paths are exercised only against fake SDKs in the notebook tests.

Before the first release: add a dependency lockfile (`uv lock` or `pip-compile`).
