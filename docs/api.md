# API

A FastAPI service that lets creators set up shows, start episode generation and fetch RSS feeds.
It does no generation itself: it records a request in Postgres and enqueues work for the pipeline
workers.

Interactive docs are served at `/docs` (Swagger) and `/redoc`; the schema is at `/openapi.json`.

**Versioning.** The API is under `/v1`: `/v1/shows`, `/v1/episodes/{id}`, `/v1/auth/login` and so
on. Discovery and health stay at the root: `/home`, `/`, `/.well-known/api-catalog`, `/health`,
`/ready` and `/metrics`. Feed, audio, notes and PDF URLs published before `/v1` existed are already
in podcast apps, so the unversioned forms (`/feeds/...`, `/episodes/{id}/audio.wav`, and the rest)
still work. They are left out of the OpenAPI description. The web app's TypeScript types are
generated from that description (`make web-client`).

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
| POST | `/v1/auth/register` | `register` | 201 | 401, 403, 409, 422 | First account needs no token and becomes admin; later ones need an admin's token |
| POST | `/v1/auth/login` | `login` | 200 | 401, 422 | Email + password → login token (six months) |
| POST | `/v1/auth/password-reset` | `request_password_reset` | 202 | 422, 429 | Emails a single-use link (30 min); same answer for any email |
| POST | `/v1/auth/password-reset/confirm` | `confirm_password_reset` | 204 | 422, 429 | New password with the link's token; ends every sign-in |
| POST | `/v1/auth/password` | `change_password` | 204 | 401, 403 | Change your password; ends your other sign-ins |
| POST | `/v1/auth/logout` | `logout` | 204 | 401 | Revokes the token used |
| GET | `/v1/auth/me` | `whoami` | 200 | 401 | The account and token behind the request |
| GET | `/v1/auth/users` | `list_users` | 200 | 401, 403 | Page of accounts (admins) |
| POST | `/v1/auth/api-keys` | `create_api_key` | 201 | 401, 422 | New API key, shown once (six months) |
| GET | `/v1/auth/api-keys` | `list_api_keys` | 200 | 401 | Page of your keys, without the keys |
| DELETE | `/v1/auth/api-keys/{token_id}` | `revoke_api_key` | 204 | 401, 404 | Revoke one of your keys |
| POST | `/v1/auth/browser-session` | `start_session` | 200 | 401, 422, 429 | The web app's sign-in: sets the HttpOnly session cookie and the CSRF cookie; no token in the body |
| DELETE | `/v1/auth/browser-session` | `end_session` | 204 | 403 | Signs the browser out: revokes its token and clears both cookies |
| GET | `/v1/auth/google/start` | `google_start` | 302 | 404 | Sign in with Google: redirects to Google's account chooser (open as a page) |
| GET | `/v1/auth/google/callback` | `google_callback` | 303 | 404 | Google's return: sets the session cookies and redirects into the app, or to `/login?google=<reason>` |
| GET | `/v1/auth/setup` | `setup_status` | 200 | 503 | `first_account_open`: true until the first account exists |
| POST | `/v1/auth/email` | `change_email` | 204 | 401, 403, 409 | Change your email (password to confirm); the old address is told |
| DELETE | `/v1/auth/me` | `delete_account` | 204 | 401, 403, 409 | Delete your account and all its data (password to confirm) |
| GET | `/v1/auth/sessions` | `list_sessions` | 200 | 401 | Page of your active sign-ins; `current` marks this one |
| DELETE | `/v1/auth/sessions/{token_id}` | `revoke_session` | 204 | 401, 404 | Sign out one device |
| PATCH | `/v1/auth/users/{user_id}` | `update_user` | 200 | 401, 403, 404, 409 | Role or disabled (admins); disabling ends its sign-ins |
| DELETE | `/v1/auth/users/{user_id}` | `delete_user` | 204 | 401, 403, 404, 409 | Delete another account and its data (admins) |
| GET | `/v1/auth/events` | `list_security_events` | 200 | 401, 403 | Security log: your own events; admins anyone's (`user_id`, `event` filters) |
| GET | `/home` (also `/`) | `home` | 200 | | Start here: every resource with its URI or template, methods, formats, ranges, paging and docs link; authentication; health links; conventions |
| GET, HEAD | `/.well-known/api-catalog` | `api_catalog`, `api_catalog_head` | 200 | | RFC 9727 API catalog (`application/linkset+json`) for automatic discovery |
| POST | `/v1/shows` | `create_show` | 201 | 422 | Create a show (FR1) |
| GET | `/v1/shows` | `list_shows` | 200 | 422 | Page of shows, newest first |
| GET | `/v1/shows/{show_id}` | `get_show` | 200 | 404 | |
| PATCH | `/v1/shows/{show_id}` | `update_show` | 200 | 404, 422 | Only sent fields change; `{}` is a no-op |
| DELETE | `/v1/shows/{show_id}` | `delete_show` | 204 | 404 | Cascades to items, uploads, episodes and claims |
| POST | `/v1/shows/{show_id}/episodes` | `start_episode` | 202 | 404, 503 | Enqueues ingest; a later episode is a refresh (FR8) |
| GET | `/v1/shows/{show_id}/episodes` | `list_episodes` | 200 | 404 | Page; `status` filter |
| GET | `/v1/episodes` | `list_all_episodes` | 200 | 422 | Page across shows; `status`, `show_id` filters. `status=needs_review` is the review queue |
| GET | `/v1/episodes/{episode_id}` | `get_episode` | 200 | 404 | `status`, `stage`, `error`, `approved_at`, `links` |
| GET | `/v1/episodes/{episode_id}/events` | `follow_episode` | 200 | 404 | Server-sent events while the episode is made; see below |
| DELETE | `/v1/episodes/{episode_id}` | `delete_episode` | 204 | 404, 409 | Removes audio and notes; rewrites the feed if it was published. 409 while running |
| GET | `/v1/episodes/{episode_id}/script` | `get_episode_script` | 200 | 404 | Segments, lines, claims with citations and verdicts |
| PATCH | `/v1/episodes/{episode_id}/script` | `edit_episode_script` | 200 | 404, 409, 422, 503 | Replace segments' lines while in review (FR7); re-runs the fact-check |
| POST | `/v1/episodes/{episode_id}/approve` | `approve_episode` | 200 | 404, 409, 503 | Release an episode in review to voicing |
| POST | `/v1/episodes/{episode_id}/retry` | `retry_episode` | 200 | 404, 409, 503 | Resume a failed or cancelled episode at its stage |
| POST | `/v1/episodes/{episode_id}/cancel` | `cancel_episode` | 200 | 404, 409 | Stop after the running stage |
| POST | `/v1/episodes/{episode_id}/remix` | `remix_episode` | 200 | 404, 409, 503 | Re-assemble a published episode with the show's current host effects and music, and publish it again in place; nothing is voiced |
| GET | `/v1/episodes/{episode_id}/runs` | `list_episode_runs` | 200 | 404 | Page of stage runs: seconds, model, prompt version, seed |
| GET | `/v1/episodes/{episode_id}/claims` | `list_episode_claims` | 200 | 404 | Page of claims; `supported`, `segment` filters |
| GET, HEAD | `/v1/episodes/{episode_id}/audio.wav` | `get_episode_audio`, `head_episode_audio` | 200, 206 | 404, 416 | `audio/wav` with Range support; `?download=true` |
| GET | `/v1/episodes/{episode_id}/notes.md` | `get_episode_notes` | 200 | 404 | Markdown show notes |
| GET | `/v1/shows/{show_id}/sources` | `list_show_sources` | 200 | 404 | Page of ingested sections: url, tier, hash, size |
| POST | `/v1/shows/{show_id}/uploads` | `upload_source` | 201 | 404, 413, 415 | Multipart `file`: a PDF up to `MAX_UPLOAD_MB` |
| GET | `/v1/shows/{show_id}/uploads` | `list_uploads` | 200 | 404 | Page of uploads, newest first |
| GET | `/v1/shows/{show_id}/uploads/{upload_id}` | `get_upload` | 200 | 404 | |
| GET | `/v1/shows/{show_id}/uploads/{upload_id}/file` | `download_upload` | 200 | 404 | The PDF; citations link here with `#page=N` |
| DELETE | `/v1/shows/{show_id}/uploads/{upload_id}` | `delete_upload` | 204 | 404 | Its sections leave at the next episode |
| GET | `/v1/feeds/{show_id}/rss.xml` | `get_show_feed` | 200 | 404 | `application/rss+xml` |
| GET | `/v1/usage` | `usage_today` | 200 | 401 | Today's Gemini requests used and left per model, and what writes and voices episodes |
| GET | `/v1/speech/engine` | `speech_engine` | 200 | 401 | Type-to-speech: the voice engine, whether recorded voices can speak, its own voices, effect presets, clips left today (Gemini) |
| POST | `/v1/speech` | `create_clip` | 202 | 404, 422, 429 | Queue a line (up to 600 characters) in a recorded or engine voice, with `delivery` and `effects`; voiced by the voice worker |
| GET | `/v1/speech` | `list_clips` | 200 | 401 | Your 20 most recent clips |
| GET | `/v1/speech/{clip_id}` | `get_clip` | 200 | 404 | Poll until `status` is `done` (then `audio`) or `failed` (then `error`) |
| GET | `/v1/speech/{clip_id}/audio.wav` | `clip_audio` | 200 | 404 | The clip, owner only; `?download=true` |
| DELETE | `/v1/speech/{clip_id}` | `delete_clip` | 204 | 404 | |
| GET | `/v1/music` | `list_music` | 200 | 401 | Built-in tracks (made in code), then your uploads |
| POST | `/v1/music` | `upload_music` | 201 | 409, 413, 415, 422 | Multipart 24 kHz mono WAV (the web app converts any format), `name`, `role`, `credit`, `rights=true` |
| GET | `/v1/music/{track_id}/audio.wav` | `music_audio` | 200 | 404 | `builtin:...` or one of yours |
| DELETE | `/v1/music/{track_id}` | `delete_music` | 204 | 404, 409 | Yours only; shows using it go back to the default for that slot |
| GET | `/health` | `health` | 200 | | Liveness only |
| GET | `/ready` | `ready` | 200 | 503 | Database, queue and storage; 503 names the failing one |
| GET | `/metrics` | | 200 | | Prometheus metrics; not in the OpenAPI schema |

**Login.** Every route under `/v1/shows`, `/episodes` (except an episode's audio and notes) and
`/shows/{id}/sources` or `/uploads` (except an upload's file) needs `Authorization: Bearer <token>`,
or, from the web app, the session cookie.
The token is a login token from `POST /auth/login` (prefix `pes_`) or an API key from
`POST /auth/api-keys` (prefix `pek_`). Both are random strings that expire 180 days after issue
(`AUTH_TOKEN_DAYS`), and both can be revoked sooner: `POST /auth/logout` for the token in use, or
`DELETE /auth/api-keys/{id}`. Only an HMAC-SHA256 of each is stored, keyed with a secret held in
Vault. Passwords are hashed with Argon2id and need at least 12 characters. A wrong email and a
wrong password get the same answer and take the same time. The first account to register becomes
the admin, and only an admin can add accounts after that. Public, so podcast apps and listeners
can use them: discovery (`/home`, `/.well-known/api-catalog`), `/auth/login` and `/auth/register`,
`/health`, `/ready`, feeds, episode audio and notes, and uploaded PDFs (their URLs carry random ids).
Without a token key configured, login answers 503.

**Browser sign-in** (after OWASP's session and CSRF guidance). The web app signs in with
`POST /v1/auth/browser-session`, never with a token it can read:

- **The session cookie**, `pe_session`, holds the login token. It is `HttpOnly`, so page scripts
  (an injected one included) cannot read it. It is `SameSite=Strict` and `Path=/`, and lasts as
  long as the token, six months. It is `Secure` when `PUBLIC_WEB_URL` is https.
- **The CSRF cookie**, `pe_csrf`, is readable by the page. It holds an HMAC of the session's id
  (signed double-submit). Every request that changes something must send it back in
  `X-CSRF-Token`, or it gets 403. Other sites cannot read the cookie, so they cannot forge the
  header.
- **Bearer tokens and API keys** are unchanged and need no CSRF token, since nothing sends them
  automatically. The cookie accepts only login tokens, never an API key.
- **Signing out**, `DELETE /v1/auth/browser-session`, revokes the token and clears both cookies,
  even if the token had already stopped working.

**Sign in with Google** (OpenID Connect's authorization-code flow with PKCE, all on the server).
It is offered when `GOOGLE_CLIENT_ID` and the `google_client_secret` are set; `GET /v1/auth/setup`
then answers `google_sign_in: true` and the sign-in and sign-up pages show the button.

- `GET /v1/auth/google/start` sends the browser to Google with a random `state`, a `nonce` and a
  PKCE challenge. They travel in `pe_google`, an HMAC-signed, `HttpOnly` cookie that lasts ten
  minutes. It is `SameSite=Lax`, because it must come back on the cross-site redirect from Google.
- `GET /v1/auth/google/callback` checks the cookie and `state`, exchanges the code (with the PKCE
  verifier) at Google's token endpoint, and checks the ID token's issuer, audience, expiry, nonce
  and `email_verified`. The token comes straight from Google over TLS, so its signature is not
  checked again (OpenID Connect Core 3.1.3.7).
- The account with that email signs in, getting the same session cookies as a password sign-in.
  With no such account, one is created (a `creator`, with no usable password until a reset) only
  while `SIGNUP_OPEN` is true. A disabled account cannot sign in this way either.
- Failures go back to `/login?google=<reason>`: `cancelled`, `expired`, `unverified`,
  `no_account`, `busy` or `failed`. Each attempt is in the security log (`method: google`).

**Live progress.** `GET /v1/episodes/{id}/events` is a stream of server-sent events. An `episode`
event (status, stage, step of 8, error, rewrite count, `running`) is sent whenever any of them
changes. A comment line every 15 seconds keeps proxies from closing the connection. The stream
ends once nothing is running (published, in review, unchanged, cancelled or failed), or after an
hour, when the browser reconnects by itself. A deleted episode ends it with a `gone` event. It
polls the database once a second with a short-lived connection of its own, so an open stream
holds neither a request's connection nor a worker thread. nginx passes it through unbuffered.

**Attempt limits** (after OWASP's authentication guidance):

- **Account lock:** five failed logins on one account within 15 minutes lock it for 15 minutes.
  The lock is temporary, and a password reset lifts it. The answer stays "wrong email or password"
  throughout, and unknown emails are counted the same way, so a lock reveals nothing.
- **Per-address limit:** 50 failures from one address in 15 minutes get `429` with `Retry-After`.
- **Shared and private:** the counters are in Redis, shared by every API process, and keyed by a
  hash of the email.
- **All settable:** `LOGIN_MAX_FAILURES`, `LOGIN_IP_MAX_FAILURES`, `LOGIN_WINDOW_MINUTES` and
  `LOGIN_LOCKOUT_MINUTES`.

**Password reset** (after OWASP's forgot-password guidance):

- **The request** answers the same for any email, and sends the email after the response.
- **The link** is single-use, valid for 30 minutes, and only the newest one works. It is stored
  only as an HMAC. It is built from `PUBLIC_WEB_URL`, never from the request, and carries the
  token in the fragment (`/reset-password#token=...`), which browsers never send to servers.
- **Confirming** sets the password, revokes every token and API key, lifts any lock, emails a
  notice, and does not sign you in.
- **Limits:** three requests per account per hour, and per-address limits on guessing tokens.
- **Changing your password** while signed in ends your other sign-ins.

**Ownership.** Every show belongs to the account that created it, and everything under it
(episodes, sources, uploads, claims, runs) follows from that. A user sees only their own shows.
Another user's show, episode or upload answers 404, the same as one that does not exist. Admins
are no exception. See [the data model](erd.md).

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
curl -o episode.wav localhost:8000/v1/episodes/<episode_id>/audio.wav              # whole file
curl -H 'Range: bytes=0-1023' -i localhost:8000/v1/episodes/<episode_id>/audio.wav  # 206, first KiB
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
TOKEN=$(curl -s localhost:8000/v1/auth/login -H 'content-type: application/json' \
  -d '{"email": "you@example.org", "password": "your passphrase"}' | jq -r .access_token)
curl -X POST localhost:8000/v1/shows -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"topic": "Open-source AI research", "sources": ["https://export.arxiv.org/rss/cs.CL"]}'
curl -X POST -H "Authorization: Bearer $TOKEN" localhost:8000/v1/shows/<show_id>/episodes  # 202
curl -H "Authorization: Bearer $TOKEN" localhost:8000/v1/episodes/<episode_id>          # status
curl -N -H "Authorization: Bearer $TOKEN" localhost:8000/v1/episodes/<episode_id>/events  # live
```

## Behaviour worth knowing

- **Starting an episode** commits the episode row *before* enqueuing the first stage, so a worker
  can always find it. If the queue is unreachable, the episode is marked `failed` and the client
  gets `503`, so nothing sits in `queued` forever.
- **Type-to-speech is a job, not a request.** `POST /v1/speech` stores the clip as `queued` and
  sends it to the voice queue, so whichever worker has the voices makes it: Chatterbox with the
  recordings (`make voice-host` on the Mac) or Gemini. A recorded voice on a Gemini server fails
  with a plain reason. With Gemini, clips may use only half of the day's voice budget.
- **Host effects and music are applied at assembly**, never at synthesis: the TTS cache keeps the
  raw voices, so changing them voices nothing again, and `remix` hears the change on a published
  episode for free. Built-in music is synthesised in code (`common/music.py`), so the API and the
  assemble worker play the same audio and the repository holds no music files.
- **Each repository write commits by itself.** There is no multi-statement unit of work yet; add
  one if an operation ever needs to change two tables atomically.
- **Errors** follow one path: services raise `NotFoundError` or `PipelineUnavailableError`
  ([errors.py](../src/podcast_engine/api/errors.py)); controllers call `to_http` to turn them into
  `404` / `503`. Anything else is a 500.

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
