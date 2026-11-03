# AI Podcast Engine

Turns live, changing sources into a grounded, multi-voice podcast episode. Each episode is
assembled at generation time from current sources, with every factual claim tied to a cited
passage. The PRD (goals, requirements FR1–FR13, evaluation plan) and the research proposal are
kept with the other research material in `research/`, which is git-ignored and stays local.

## Pipeline

```
ingest → index → retrieve_plan → script ⇄ factcheck → voice → assemble → publish
```

Every stage has its own Redis queue, so it retries on its own. Five worker containers serve the
eight queues, grouped by what they need installed (`ingest_publish`, `index_plan`,
`script_factcheck`, `voice`, `assemble`); scale a group with `docker compose up -d --scale`.
Workers are stateless:
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
  worker.py        `python -m podcast_engine.worker <stage> [<stage> ...]`
  pipeline.py      `python -m podcast_engine.pipeline`: every stage in one process (tests, host runs)
web/               React + Vite UI, served by nginx
db/init/           SQL run when the Postgres volume is first created
db/migrations/     idempotent SQL applied by the `db-migrate` service on every `up`
config/            show definitions, source reliability tiers, pronunciation lexicon
prompts/           versioned prompts (`<name>.v<N>.md`), logged per episode
assets/audio/      intro/outro/transition audio
docs/              api.md (the API), erd.md (the data model), observability.md (metrics and logs)
monitoring/        Prometheus scrape configuration
docker/            stage.Dockerfile, the one recipe behind every Python image (api and worker targets)
tests/             unit/ (no services needed), integration/ (marked `integration`)
research/          git-ignored, local only: PRD, proposal, presentation, reports, notebooks, and the
                   RQ1–RQ3 evaluation code and results (`make -C research help`)
```

## Docker

`docker-compose.yml` runs five pipeline workers plus `api`, `web`, `scheduler`, Postgres,
Redis and RustFS (S3-compatible; MinIO no longer publishes images). Python images share `docker/stage.Dockerfile`; build args pick the extras and
system packages each worker needs (for example only `assemble` installs `ffmpeg`). The one-shot
jobs (`vault-certs`, `vault-init`, `s3-init`, `db-migrate`) and the scheduler share one image,
`podcast-engine-tools`.

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
| ingest_publish (ingest, publish) | `ingest_cache` → `/data/ingest`; `uploads` (ro); `feed_staging` → `/data/feeds`; `./config` (ro) |
| index_plan (index, retrieve_plan) | `hf_cache` → `/home/app/.cache/huggingface`; `./config` (ro); `./prompts` (ro) |
| script_factcheck (script, factcheck) | `./config` (ro); `./prompts` (ro) |
| voice | `hf_cache`; `tts_cache` → `/data/tts_cache`; `audio_scratch` → `/data/audio`; `./config` (ro); `./assets` (ro) |
| assemble | `audio_scratch` → `/data/audio`; `./assets` (ro) |
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
make -C research notebook-test  # runs the notebook offline (only where research/ exists)
```

## Web app

The web app is at http://localhost:8080 (`make up`). It is React and Vite, in white and dark orange,
served by nginx in front of the API. On a fresh stack it asks you to create the first account (the
admin), then signs you in. From there you can:

- **Shows:** create, edit and delete them, see their sources, and upload PDFs.
- **Episodes:** generate one, then follow its progress live, step by step.
- **Review:** read the script with its fact-check verdicts, edit lines, and approve it.
- **Results:** listen to the audio, read the show notes, and see what each stage ran.

Sign-in is a secure cookie the page cannot read, and changes carry a CSRF token (see
[docs/api.md](docs/api.md)). The pages aim at WCAG 2.0 AA: AA contrast, labelled fields, keyboard
tabs and dialogs, a skip link, and progress announced to screen readers.

```bash
cd web && npm ci
npm run dev           # http://localhost:5173, proxies /api to the API on :8000
npm test              # Vitest + Testing Library
npm run build         # type-check, then build into web/dist
make web-client       # after changing the API: regenerate web/src/api/schema.d.ts
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
docker compose restart index_plan script_factcheck voice   # services read secrets at start

# replace a secret (a leaked key, say): put the new value in secrets/<name>.txt, then
make rotate-secret NAME=llm_api_key   # or tts_api_key, smtp_password, google_client_secret, search_api_key
# and revoke the old value with its provider (AI Studio, Google Cloud Console, ...)

# the first account becomes the admin; then log in for a six-month token
curl -X POST localhost:8000/v1/auth/register -H 'content-type: application/json' \
  -d '{"email": "you@example.org", "password": "a long passphrase of your own"}'
TOKEN=$(curl -s -X POST localhost:8000/v1/auth/login -H 'content-type: application/json' \
  -d '{"email": "you@example.org", "password": "a long passphrase of your own"}' | jq -r .access_token)
curl -H "Authorization: Bearer $TOKEN" localhost:8000/v1/shows
```

In `/docs`, use **Authorize** and paste the token. `POST /v1/auth/api-keys` creates a key for scripts.
It also lasts six months.

## Running an episode

The stages implement the flow validated in the pipeline notebook (`research/notebooks/`). A web page is split into
sections, and each section is a source with its own hash and anchor. Sections are chunked
(80 words, 40 overlap) and embedded into pgvector. Passages are ranked by topic, recency and
authority, one segment is planned per section, and a two-host script quotes or paraphrases cited
passages. The fact-check gate loops back to the script stage, then lines are voiced, mixed to
-16 LUFS and published as show notes and RSS.

```bash
curl localhost:8000/home                                   # every endpoint, auth and health
curl -X POST localhost:8000/v1/shows -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' -d '{
  "topic": "What ClickHouse is and why it is fast for analytics",
  "sources": ["https://clickhouse.com/docs/get-started/about/intro"],
  "topic_keywords": "ClickHouse column-oriented database OLAP analytics queries rows columns storage",
  "attribution": "Source material: What is ClickHouse?, ClickHouse Documentation (CC BY-NC-SA 4.0).",
  "max_segments": 6, "tone": "casual", "expertise": "beginner", "target_minutes": 3}'
curl -X POST -H "Authorization: Bearer $TOKEN" localhost:8000/v1/shows/<show_id>/episodes       # 202; starts the pipeline
curl -H "Authorization: Bearer $TOKEN" localhost:8000/v1/episodes/<episode_id>                  # status and current stage
curl -H "Authorization: Bearer $TOKEN" localhost:8000/v1/episodes/<episode_id>/script           # claims, citations, verdicts
curl -o episode.wav localhost:8000/v1/episodes/<episode_id>/audio.wav
curl localhost:8000/v1/feeds/<show_id>/rss.xml
```

Posting another episode for the same show is a **refresh** (FR8): the **Refresh** button on a
published episode. The sources are read again and the searches run again; only segments whose
sections changed are re-scripted and re-voiced, and if nothing changed the episode ends as
`unchanged`. Choosing "Everything, from scratch" (`{"rebuild": true}`) regenerates every segment
instead. Set `REFRESH_INTERVAL_HOURS` to have the scheduler refresh on a timer as well (off by
default: on the Gemini free tier, refreshing by hand keeps the day's requests for you).

**Demonstrating refresh with a source that changes.** `make demo-site` starts a fictional local
news page (*The Port Arden Ledger*, `demo/site/`) whose story moves through three editions:
1. As first published.
2. Only the Timeline section changes.
3. A new "Subscriptions open" section is added.

To run the demo:
1. Create a show with `http://demo-site:8095/` as its source. That's the address the workers use
   inside the stack; the browser opens `http://localhost:8095`.
2. Generate an episode.
3. Publish the next edition with the button on the page or `make demo-next`.
4. Press **Refresh** on the episode. Only the segment built from the changed section is
   re-scripted and re-voiced.
5. `make demo-reset` goes back to edition 1.

Citation links in that episode's notes point at `demo-site:8095`, which only resolves inside the
stack.

**Searches as sources (FR2).** Besides web pages, feeds and PDFs, a show can have up to 3
searches. Each time an episode is made, the top `SEARCH_RESULTS` results of each are read like the
show's own pages, so every section is citable and a refresh sees new results as changed sources.
The default provider is Wikipedia's search API (`SEARCH_PROVIDER=wikipedia`, no key, the show's
language): articles are read through the API as plain text, dated by their last edit, and rank as
established sources. `brave` searches the whole web with a Brave Search API key
(`secrets/search_api_key.txt`, or `make rotate-secret NAME=search_api_key`); it is paid. Google's
Custom Search JSON API is closed to new customers, so it is not offered.

| Setting (`.env`) | Default | |
|---|---|---|
| `LLM_ENABLED` | `false` | `false`: offline extractive writer and word-overlap judge, no key and no cost. `true`: `LLM_PROVIDER`/`LLM_MODEL` (Gemini `gemini-3.8-flash`, or `anthropic`) plan, write and judge, with the key in `secrets/llm_api_key.txt` |
| `EMBEDDING_MODEL` | `hashing` | Offline. A sentence-transformers id works if it has 384 dimensions (for example `BAAI/bge-small-en-v1.5`) |
| `TTS_BACKEND` | `placeholder` | `placeholder` (tones, for testing) or `gemini` (prebuilt voices, key in `secrets/tts_api_key.txt`, else the LLM key) in containers. `say` and `chatterbox` run on a host, see below |
| `TTS_REQUESTS_PER_MINUTE` | `0` | `gemini` only: space voice requests out to this rate (the free tier allows 3 a minute); `0` = no limit. Rate-limited requests are retried after the wait Gemini asks for |
| `LLM_REQUESTS_PER_DAY` | `0` | Gemini text requests `LLM_MODEL` (and `LLM_FALLBACK_MODEL`) may make per Pacific day, counted in Redis across every worker and the API; `0` = not counted. Set it just under your daily cap (AI Studio, Rate limits; the free tier is about 20). An episode starts only if the day can finish it (outline, one request per segment, fact-check), and those requests are then reserved for it, so the bot and other episodes cannot spend them; the reservation is released when it ends, fails or pauses for review. If `LLM_MODEL` cannot cover it, it is reserved on `LLM_FALLBACK_MODEL`. Only requests Gemini served or rejected count: overloaded 503s, 429s and network failures do not. A rewrite the day cannot cover is held for review, the companion bot uses at most half of the day, and the script is saved segment by segment, so a retry writes only what is missing. `python -m podcast_engine.common.quota` prints today's counts and reservations |
| `TTS_REQUESTS_PER_DAY` | `0` | The same for `TTS_MODEL`: one request per part read aloud, so an episode needs its segments plus 3. The free tier is about 15 |
| `ASSISTANT_QUESTIONS_PER_HOUR` | `20` | Questions each person may ask the companion bot an hour. With `LLM_ENABLED=true` each one is a model call; otherwise the built-in help answers |
| `SIGNUP_OPEN` | `false` | `true`: anyone can create their own `creator` account at `/signup` (throttled per address). Each account can spend your LLM and TTS quota |
| `GOOGLE_CLIENT_ID` | blank | Shows "Sign in with Google". Create an OAuth client (type *Web application*) in Google Cloud Console with the redirect URI `<PUBLIC_WEB_URL>/api/v1/auth/google/callback`, and put its secret in `secrets/google_client_secret.txt` (vault-init stores it in Vault) |
| `MAX_REWRITES` | `2` | Gate loops before an episode is held as `needs_review` |
| `REFRESH_INTERVAL_HOURS` | `0` | Scheduler refresh period for published shows; `0` is off (use the Refresh button) |
| `SEARCH_PROVIDER` | `wikipedia` | Where a show's searches look: `wikipedia` (no key), `brave` (paid, key in `secrets/search_api_key.txt`) or `off` |
| `SEARCH_RESULTS` | `3` | Top results read for each search (1 to 10) |

**Cloned voices (Chatterbox) run on the host.** Chatterbox needs torch and ideally a GPU (MPS on a
Mac), and Docker on macOS cannot reach the Mac's GPU, so Chatterbox is not in the voice image.
`make voice-host` runs the voice worker from `.venv-cloning` against the stack, with its own overlay,
`docker-compose.voice-host.yml`, which publishes the database, queue and storage ports (the S3 API
on 9010; it reads `.env`). Keep it running while episodes are voiced; stop it with Ctrl-C. Set
`COMPOSE_FILE=docker-compose.yml:docker-compose.voice-host.yml` in `.env` so that every
`docker compose` command keeps those ports. The voice container checks for its backend before
taking any job: without Chatterbox it logs why and stops (`voice_worker_standing_down`), so jobs
wait in the queue for the host worker instead of failing.

**Voice consent.** Before recording, the voice studio shows the consent form in full as a
document; agreement is possible only after scrolling to its end. The same form is at
`GET /v1/voices/consent.pdf`, to keep or print: a printed copy signed by the speaker can serve as
the written permission for someone else's voice. Each voice stores the version and full text its
speaker agreed to, so voices signed on an earlier version keep that record. Deleting a voice
withdraws consent: the recording and the speech clips made with it go from storage, and the
voicing worker deletes its working copy before it next voices an episode. The form's text is
`CONSENT_SECTIONS` in `api/models/voices_model.py`; every claim in it about the software is checked
against the code, so a change to how voices are stored or used must update it (and its version). `config/voices.yaml` holds the consent
record each cloned voice needs. Voices recorded in the voice studio and assigned to a show's hosts
replace the file's entry for that host.

Each script line carries a delivery (neutral, warm, curious, excited, thoughtful, amused, serious)
chosen by the script writer. Chatterbox reads it through its expressiveness and pace
(`ChatterboxBackend.STYLES`), Gemini as a speaking style, and the assembly paces the turns from it:
answers and quick reactions come in fast, a fact gets a moment to land.

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
scheduler and the Refresh button; web pages, RSS/Atom feeds, uploaded PDFs and search results as
sources; review and editing before
voicing (`review_before_voice`, the review queue at `/episodes?status=needs_review`); retry,
cancel and delete; paginated lists. Tested end to end against Postgres with offline settings
([tests/integration/](tests/integration/)). Not built yet: pages behind authentication, and MP3
output. Each user sees only their own shows
([docs/erd.md](docs/erd.md)).
The Gemini and Claude paths are exercised only against fake SDKs in the notebook tests.

Before the first release: add a dependency lockfile (`uv lock` or `pip-compile`).
