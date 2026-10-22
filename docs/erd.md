# Data model (ERD)

Postgres holds every record the API and the pipeline share. The schema is `db/init/` plus
`db/migrations/0003` to `0008`. This diagram was checked against the foreign keys in a migrated
database.

```mermaid
erDiagram
    users ||--o{ auth_tokens : "signs in with (sessions and API keys)"
    users ||--o{ password_resets : "resets its password with"
    users |o--o{ security_events : "is the subject of"
    users ||--o{ shows : owns
    shows ||--o{ uploads : "has source files"
    shows ||--o{ source_items : "is built from"
    source_items ||--o{ chunks : "is split into"
    shows ||--o{ episodes : has
    episodes ||--o{ segments : "is planned as"
    episodes ||--o{ claims : states
    segments |o--o{ claims : contains
    episodes ||--o{ stage_runs : "is produced by"

    users {
        uuid user_id PK
        text email UK "unique, case-insensitive"
        text password_hash "Argon2id"
        text role "admin or creator"
        bool disabled
        timestamptz created_at
    }
    auth_tokens {
        uuid token_id PK
        uuid user_id FK
        text kind "session (a sign-in) or api_key"
        text name
        text token_hash UK "HMAC-SHA256; the token itself is never stored"
        text prefix
        timestamptz expires_at "six months after issue"
        timestamptz last_used_at
        timestamptz created_at
        timestamptz revoked_at "logout, sign-out of a device, disable, password change"
    }
    password_resets {
        uuid reset_id PK
        uuid user_id FK
        text token_hash UK "HMAC-SHA256 of the emailed link's token"
        timestamptz created_at
        timestamptz expires_at "30 minutes after issue"
        timestamptz used_at "single use; also set when a newer link replaces it"
    }
    security_events {
        uuid event_id PK
        uuid user_id FK "set null when the account is deleted"
        text event "login_failed, account_locked, api_key_created, ..."
        text address "the client's IP"
        jsonb detail "extra facts, never secrets"
        timestamptz created_at
    }
    shows {
        uuid show_id PK
        uuid owner_id FK "users; null only for shows made before login"
        text topic
        text tone
        int target_minutes
        int host_count
        jsonb sources "page and feed URLs"
        text topic_keywords
        int max_segments
        text ranking_profile
        bool review_before_voice
    }
    uploads {
        uuid upload_id PK
        uuid show_id FK
        text filename
        bigint size_bytes
        text object_key "the PDF in object storage"
    }
    source_items {
        uuid item_id PK
        uuid show_id FK
        text url UK "unique per show"
        text title
        text text
        text content_hash "change detection"
        text reliability
        int position
    }
    chunks {
        uuid chunk_id PK
        uuid item_id FK
        int position UK "unique per item"
        text text
        vector embedding "pgvector, 384 dimensions"
    }
    episodes {
        uuid episode_id PK
        uuid show_id FK
        text status
        text stage
        int revision
        int rewrite_count
        jsonb script
        jsonb fact_check
        text audio_key "WAV"
        text audio_mp3_key "MP3, for feeds and players"
        text notes_key
        timestamptz approved_at
        timestamptz published_at
    }
    segments {
        uuid segment_id PK
        uuid episode_id FK
        int position UK "unique per episode"
        text title
        uuid_array source_item_ids
        uuid_array chunk_ids
        bool needs_script
    }
    claims {
        uuid claim_id PK
        uuid episode_id FK
        uuid segment_id FK "set null if the segment goes"
        text text
        uuid_array chunk_ids "the cited passages"
        bool supported
        text reason
    }
    stage_runs {
        uuid run_id PK
        uuid episode_id FK
        text stage
        text model
        text prompt_version
        bigint seed
        numeric seconds
    }
```

## Accounts, sign-ins and the security log

- **A session is a sign-in:** one browser or device that logged in. Sessions and API keys are both
  rows in `auth_tokens`, told apart by `kind`, because they authenticate the same way and share
  expiry and revocation. `GET /auth/sessions` lists a user's active sessions; `DELETE
  /auth/sessions/{token_id}` ends one. Only an HMAC of each token is stored.
- **Password resets** are single-use, short-lived rows. Requesting a new link voids older ones.
- **The security log** (`security_events`) records sign-ins, failures, locks, throttling, resets,
  password and email changes, API keys and account changes. It is append-only. When an account is
  deleted its entries stay, with `user_id` set to null; the deletion entry itself names the
  account in `detail.account`. Failed logins for unknown emails have no `user_id` and only a hash
  of the email.

## Ownership

**A show belongs to one user** (`shows.owner_id`), and everything else hangs off a show by foreign
key:

- uploads and source items belong to a show;
- chunks belong to a source item;
- episodes belong to a show;
- segments, claims and stage runs belong to an episode.

So one owner column decides who can reach every record, and there is no second copy of ownership
to drift out of step.

- **The API scopes every protected query to the caller.** Shows filter on `owner_id`. Episodes,
  sources and uploads are reached through a show the caller owns. Another user's record answers
  404, exactly like one that does not exist, so ids cannot be probed.
- **Admins are no exception.** An admin manages accounts but sees only their own shows.
- **Public by design:** episode audio, show notes, feeds and uploaded PDFs. Podcast apps and
  listeners fetch them without logging in, by URLs that carry random ids.
- **Shows made before login existed** have no owner. The first account to register (the admin)
  takes them over. The API never creates a show without an owner, and never shows an unowned one.

## Deleting

Deletes cascade down the tree:

- **Deleting a user** deletes their tokens, reset links and shows, and unlinks (keeps) their
  security log entries.
- **Deleting a show** deletes its uploads, source items (and their chunks) and episodes.
- **Deleting an episode** deletes its segments, claims and stage runs.

Files in object storage (WAV and MP3 audio, notes, feeds, uploaded PDFs) are removed by the API's
delete endpoints for episodes, uploads and accounts (`DELETE /auth/me`, `DELETE
/auth/users/{user_id}`). Deleting a show, or deleting anything through SQL directly, leaves those
files behind.
