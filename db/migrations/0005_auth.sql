-- Login: users with passwords, and the tokens they authenticate with. Idempotent, like 0003.

CREATE TABLE IF NOT EXISTS users (
  user_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email         text NOT NULL,
  password_hash text NOT NULL,                      -- Argon2id, with its parameters and salt
  role          text NOT NULL DEFAULT 'creator' CHECK (role IN ('admin', 'creator')),
  disabled      boolean NOT NULL DEFAULT false,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS users_email_idx ON users (lower(email));

-- Login sessions and API keys. Only an HMAC of each token is stored (its key is in Vault), so a
-- copy of this table does not let anyone sign in. Every token expires; revoking sets revoked_at.
CREATE TABLE IF NOT EXISTS auth_tokens (
  token_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid NOT NULL REFERENCES users ON DELETE CASCADE,
  kind         text NOT NULL CHECK (kind IN ('session', 'api_key')),
  name         text NOT NULL DEFAULT '',             -- an API key's label
  token_hash   text NOT NULL UNIQUE,
  prefix       text NOT NULL,                        -- the first characters, to recognise a key
  created_at   timestamptz NOT NULL DEFAULT now(),
  expires_at   timestamptz NOT NULL,
  last_used_at timestamptz,
  revoked_at   timestamptz
);
CREATE INDEX IF NOT EXISTS auth_tokens_user_idx ON auth_tokens (user_id, kind, created_at DESC);
