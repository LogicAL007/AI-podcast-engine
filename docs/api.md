# API

A FastAPI service that lets creators set up shows, start episode generation and fetch RSS feeds.
It does no generation itself: it records a request in Postgres and enqueues work for the pipeline
workers.

Interactive docs are served at `/docs` (Swagger) and `/redoc`; the schema is at `/openapi.json`.

## Structure

One folder per layer under [src/podcast_engine/api/](../src/podcast_engine/api/), and one file
per resource inside each, named `<resource>_<layer>.py`:

```
api/
  main.py            builds the FastAPI app and mounts the routers
  dependencies.py    wires layers together (sessions, repositories, queue, storage)
  errors.py          domain errors and their HTTP mapping
  routers/           shows_router.py       episodes_router.py       feeds_router.py
  controllers/       shows_controller.py   episodes_controller.py   feeds_controller.py
  services/          shows_service.py      episodes_service.py      feeds_service.py
  models/            shows_model.py        episodes_model.py        feeds_model.py
  repositories/      shows_repository.py   episodes_repository.py
```

| Layer | Job |
|---|---|
| router | paths, status codes, query params, OpenAPI metadata |
| controller | calls the service, translates domain errors into HTTP errors |
| service | business rules; knows nothing about HTTP or SQL |
| model | Pydantic request and response schemas |
| repository | SQL for the resource |

There is no `feeds_repository.py`: feeds are files in object storage, read through the
`ObjectStore` interface, so `feeds_service.py` takes the store directly.

### Request flow

```
HTTP request
  → router      validates path, query and body against models.py
  → controller  one method per operation
  → service     applies rules, raises DomainError on failure
  → repository  runs SQL and returns models
HTTP response   ← controller turns a DomainError into 404 / 503
```

### Layer rules

| Layer | May import | Must not |
|---|---|---|
| router | controller, models, `dependencies` | contain logic; touch services or repositories |
| controller | service, models, `errors` | run SQL; contain business rules |
| service | repository interfaces, models, `errors` | import FastAPI; run SQL |
| repository | SQLAlchemy, models | import FastAPI; raise HTTP errors |

Services and controllers depend on a repository **Protocol**, not on Postgres. That is what lets
the unit tests run the whole API with in-memory fakes.

## Endpoints

| Method | Path | Operation id | Success | Errors | Notes |
|---|---|---|---|---|---|
| GET | `/home` (also `/`) | `home` | 200 | | Start here: every resource with its URI or template, methods, formats, ranges, paging and docs link; authentication; health links; conventions |
| GET, HEAD | `/.well-known/api-catalog` | `api_catalog`, `api_catalog_head` | 200 | | RFC 9727 API catalog (`application/linkset+json`) for automatic discovery |
| POST | `/shows` | `create_show` | 201 | 422 | Create a show (FR1) |
| GET | `/shows` | `list_shows` | 200 | 422 | Page of shows, newest first |
| GET | `/shows/{show_id}` | `get_show` | 200 | 404 | |
| PATCH | `/shows/{show_id}` | `update_show` | 200 | 404, 422 | Only sent fields change; `{}` is a no-op |
| DELETE | `/shows/{show_id}` | `delete_show` | 204 | 404 | Cascades to items, uploads, episodes and claims |
| POST | `/shows/{show_id}/episodes` | `start_episode` | 202 | 404, 503 | Enqueues ingest; a later episode is a refresh (FR8) |
| GET | `/shows/{show_id}/episodes` | `list_episodes` | 200 | 404 | Page; `status` filter |
| GET | `/episodes` | `list_all_episodes` | 200 | 422 | Page across shows; `status`, `show_id` filters. `status=needs_review` is the review queue |
| GET | `/episodes/{episode_id}` | `get_episode` | 200 | 404 | `status`, `stage`, `error`, `approved_at`, `links` |
| DELETE | `/episodes/{episode_id}` | `delete_episode` | 204 | 404, 409 | Removes audio and notes; rewrites the feed if it was published. 409 while running |
| GET | `/episodes/{episode_id}/script` | `get_episode_script` | 200 | 404 | Segments, lines, claims with citations and verdicts |
| PATCH | `/episodes/{episode_id}/script` | `edit_episode_script` | 200 | 404, 409, 422, 503 | Replace segments' lines while in review (FR7); re-runs the fact-check |
| POST | `/episodes/{episode_id}/approve` | `approve_episode` | 200 | 404, 409, 503 | Release an episode in review to voicing |
| POST | `/episodes/{episode_id}/retry` | `retry_episode` | 200 | 404, 409, 503 | Resume a failed or cancelled episode at its stage |
| POST | `/episodes/{episode_id}/cancel` | `cancel_episode` | 200 | 404, 409 | Stop after the running stage |
| GET | `/episodes/{episode_id}/runs` | `list_episode_runs` | 200 | 404 | Page of stage runs: seconds, model, prompt version, seed |
| GET | `/episodes/{episode_id}/claims` | `list_episode_claims` | 200 | 404 | Page of claims; `supported`, `segment` filters |
| GET, HEAD | `/episodes/{episode_id}/audio.wav` | `get_episode_audio`, `head_episode_audio` | 200, 206 | 404, 416 | `audio/wav` with Range support; `?download=true` |
| GET | `/episodes/{episode_id}/notes.md` | `get_episode_notes` | 200 | 404 | Markdown show notes |
| GET | `/shows/{show_id}/sources` | `list_show_sources` | 200 | 404 | Page of ingested sections: url, tier, hash, size |
| POST | `/shows/{show_id}/uploads` | `upload_source` | 201 | 404, 413, 415 | Multipart `file`: a PDF up to `MAX_UPLOAD_MB` |
| GET | `/shows/{show_id}/uploads` | `list_uploads` | 200 | 404 | Page of uploads, newest first |
| GET | `/shows/{show_id}/uploads/{upload_id}` | `get_upload` | 200 | 404 | |
| GET | `/shows/{show_id}/uploads/{upload_id}/file` | `download_upload` | 200 | 404 | The PDF; citations link here with `#page=N` |
| DELETE | `/shows/{show_id}/uploads/{upload_id}` | `delete_upload` | 204 | 404 | Its sections leave at the next episode |
| GET | `/feeds/{show_id}/rss.xml` | `get_show_feed` | 200 | 404 | `application/rss+xml` |
| GET | `/health` | `health` | 200 | | Liveness only |
| GET | `/ready` | `ready` | 200 | 503 | Database, queue and storage; 503 names the failing one |
| GET | `/metrics` | | 200 | | Prometheus metrics; not in the OpenAPI schema |

**Discovery.** `/home` is a JSON home document ([draft-nottingham-json-home-06](https://datatracker.ietf.org/doc/html/draft-nottingham-json-home)):
`api` holds the title, version, links (by [RFC 8631](https://www.rfc-editor.org/rfc/rfc8631)
relation: `service-desc` is the OpenAPI description, `service-doc` the interactive docs, `status`
the liveness check), and this API's own additions `auth`, `health` and `conventions`; `resources`
maps a link relation (`tag:podcast-engine,2026:episode-audio`) to the resource's `href` or
`hrefTemplate` and `hints` (`allow`, `formats`, `acceptPost`, `acceptPatch`, `acceptRanges`,
`docs`, `authSchemes`), plus an `operations` list per resource. It is generated from the routes, so
it always matches them. Send `Accept: application/json-home` for that media type; otherwise it is
`application/json`. Every response from `/home` carries a `Link` header with the same relations.
`/.well-known/api-catalog` ([RFC 9727](https://www.rfc-editor.org/rfc/rfc9727)) is the
machine-discovery entry, pointing to `/home`, the OpenAPI description, the docs and `/health`.
Links are absolute and include the `/api` prefix behind the web proxy (`X-Forwarded-Prefix`).

**Lists** return a page: `{"items": [...], "total": 42, "limit": 20, "offset": 0, "next": "..."}`.
`limit` is 1–100 (default 20) and `offset` ≥ 0; `next` is the path and query of the next page,
keeping any filters, or null on the last page. Ordering always ends with an id, so pages never
repeat or skip an item.

**Review.** An episode is `needs_review` when the fact-check held it back after its rewrites, or,
for a show with `review_before_voice`, when its script passed and waits for approval. Edit it with
`PATCH .../script` (a line with `chunk_ids` is a claim citing those passages; without, framing), or
release it with `POST .../approve`. An edited script is fact-checked again but never regenerated
over the edit: if it fails, it returns to review.

**Lifecycle.** `cancel` works while an episode is queued, processing or in review; the running stage
finishes and nothing runs after it. `retry` resumes a failed or cancelled episode at the stage where
it stopped. `DELETE` refuses a running episode (cancel it first).

**Sources.** A show's `sources` may be web pages or RSS/Atom feeds. Each feed entry with a usable
summary becomes a section; an entry with no summary or only a teaser is read from its linked page.
Uploaded PDFs are split at their headings (or per page) and cited with a link to the page.

Interactive docs are at `/docs` (Swagger UI) and `/redoc`; the schema is at `/openapi.json`. Every
error body is `{"detail": "..."}` (the `ErrorDetail` schema), except 422 validation errors, which
use FastAPI's `HTTPValidationError`. Operation ids are the route function names, so generated
clients get methods such as `get_episode_audio`. The links in `EpisodeRead.links` are relative to
the API's base URL (`/api` behind the web proxy).

```bash
curl -o episode.wav localhost:8000/episodes/<episode_id>/audio.wav              # whole file
curl -H 'Range: bytes=0-1023' -i localhost:8000/episodes/<episode_id>/audio.wav  # 206, first KiB
```

Show fields: `topic` (3–200 chars), `tone` (`casual`, `neutral`, `formal`), `target_minutes`
(1–30, default 7), `host_count` (1–4, default 2), `language` (`en` or `fr-CA` form),
`expertise` (`beginner`, `intermediate`, `expert`), `sources` (up to 50 http(s) URLs),
`topic_keywords` (words matched with the topic when ranking passages), `attribution` (credit and
licence line for the show notes), `max_segments` (1–12, default 6), `ranking_profile` (`explainer`
favours authoritative sources, `daily` fresh ones).

Episode `status` is `queued`, `processing` (see `stage`), `needs_review` (the gate held it after
the last rewrite; `error` says why), `published`, `unchanged` (a refresh found no changed source)
or `failed` (`error` names the stage and the reason).

```bash
curl -X POST localhost:8000/shows -H 'content-type: application/json' \
  -d '{"topic": "Open-source AI research", "sources": ["https://export.arxiv.org/rss/cs.CL"]}'
curl -X POST localhost:8000/shows/<show_id>/episodes      # 202, returns the episode
curl localhost:8000/episodes/<episode_id>                  # poll status
```

## Behaviour worth knowing

- **Starting an episode** commits the episode row *before* enqueuing the first stage, so a worker
  can always find it. If the queue is unreachable, the episode is marked `failed` and the client
  gets `503`, so nothing sits in `queued` forever.
- **Each repository write commits by itself.** There is no multi-statement unit of work yet; add
  one if an operation ever needs to change two tables atomically.
- **Errors** follow one path: services raise `NotFoundError` or `PipelineUnavailableError`
  ([errors.py](../src/podcast_engine/api/errors.py)); controllers call `to_http` to turn them into
  `404` / `503`. Anything else is a 500.
- **No authentication yet.** Every route is open, so run it only behind a trusted network.
  Compose binds the API to `127.0.0.1`.

## Running

**Docker** (the whole stack; the API image runs uvicorn):

```bash
make up                               # API on http://localhost:8000, UI on :8080
make dev                              # same, with ./src mounted and uvicorn --reload
```

The image is the `api` target of [docker/stage.Dockerfile](../docker/stage.Dockerfile). Its command
is `uvicorn podcast_engine.api.main:app`, configured through `UVICORN_*` environment variables
(uvicorn reads them natively): host `0.0.0.0` and port `8000` are preset in the image, and compose
sets `UVICORN_WORKERS` from `API_WORKERS` in `.env` (default 2). The image has its own
`HEALTHCHECK` against `/health`. It runs as a non-root user.

**Locally**, with Postgres, Redis and S3 storage from compose. The dev overlay publishes their ports
on localhost:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres redis s3 s3-init
```

```bash
make setup
export DATABASE_URL=postgresql+psycopg://podcast:change-me@localhost:5432/podcast
export REDIS_URL=redis://localhost:6379/0
make api                              # uvicorn with --reload
```

Run it from the repository root with the full module path, `podcast_engine.api.main:app`. Running
`uvicorn main:app` from inside `api/` fails with `No module named 'podcast_engine'` unless the
package is installed (`make setup`), and `--reload` would then watch only that one folder.

Run pipeline workers in Docker, not directly on your machine. On Python 3.14, Celery's prefork pool
crashes every task with `ValueError: not enough values to unpack (expected 3, got 0)`; the images use
Python 3.12, where workers run correctly. A host worker that must run on 3.14 (the Chatterbox voice
worker, see the README) sets `WORKER_POOL=solo`. The API itself runs fine on 3.14.

Settings are read from the environment ([config.py](../src/podcast_engine/common/config.py)).

## Testing

```bash
make test                             # unit tests: no services needed
pytest -m integration                 # SQL repositories against a real Postgres
```

Unit tests build the real app and replace the providers in `dependencies.py` with fakes
(`app.dependency_overrides`), so they exercise routing, validation, controllers and services end
to end. See [tests/unit/api/](../tests/unit/api/).

The integration tests ([tests/integration/test_repositories.py](../tests/integration/test_repositories.py))
need the schema from `db/init/` and `DATABASE_URL` pointing at it; they skip themselves if
Postgres is unreachable.

## Adding an endpoint

1. Add request/response schemas to the resource's `models/<resource>_model.py`.
2. Add the rule to `services/<resource>_service.py`; raise a `DomainError` subclass for failure cases.
3. If it needs data, add a method to the repository Protocol, the Postgres class and the test fake
   (`tests/unit/api/fakes.py`).
4. Add a controller method that maps the new errors with `to_http`.
5. Add the route in `routers/<resource>_router.py` with a `summary`, a `response_description`, a
   docstring (it becomes the description), `Path`/`Query` descriptions for every parameter, and
   `responses=errors(e404="...")` (from `api/openapi.py`) for each error status. Files use
   `file_response(...)`.
6. Add a test in `tests/unit/api/`. `test_openapi_docs.py` fails if any of step 5 is missing.

A new resource gets one file in each layer folder (`<resource>_router.py`, `_controller.py`,
`_service.py`, `_model.py` and, if it stores data, `_repository.py`), a provider in
`dependencies.py`, and an `include_router` line in `main.py`.

## Not built yet

- Search results as a source, and pages behind authentication.
- Authentication and per-creator ownership of shows.
