#!/usr/bin/env bash
# Ship the engine to the demo server Terraform made (infra/demo), from this Mac:
#
#   infra/demo/deploy.sh               # code and settings
#   infra/demo/deploy.sh --with-data   # also replace the server's data with this Mac's: the
#                                      # database (accounts, shows, episodes) and stored files
#                                      # (audio, registered voices). Needs the local stack running.
#
# 1. Stores .env and the secrets/*.txt keys in SSM Parameter Store (SecureString), so they never
#    enter Terraform state, the release archive or the command line.
# 2. Packs the repository's files (git's list: tracked and new, never ignored ones, so no
#    secrets/ or research/) and uploads them to the private bucket.
# 3. Runs /opt/demo/deploy.sh on the server through SSM (no SSH) and prints its output.
#
# Runs as podcast-user, the default AWS CLI profile (the make targets set AWS_PROFILE).
set -euo pipefail
cd "$(dirname "$0")/../.."  # the repository root
TERRAFORM=${TERRAFORM:-terraform}
out() { $TERRAFORM -chdir=infra/demo output -raw "$1"; }
WITH_DATA=no
[ "${1:-}" = "--with-data" ] && WITH_DATA=yes

[ -f .env ] || { echo "No .env: this deploys the Mac's settings." >&2; exit 1; }
[ -s secrets/llm_api_key.txt ] || { echo "secrets/llm_api_key.txt is empty: the server needs the Gemini key." >&2; exit 1; }
BUCKET=$(out bucket); INSTANCE=$(out instance_id); PREFIX=$(out ssm_prefix)
AWS_DEFAULT_REGION=$(out region)
export AWS_DEFAULT_REGION

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

# 1. Secrets: each request goes to the CLI as a private temporary file (removed at once), so no
#    value appears on the command line or in the process list.
mkdir -m 700 "$STAGE/secrets"
python3 - "$PREFIX" "$STAGE/secrets" <<'PY'
import json, os, sys
prefix, folder = sys.argv[1], sys.argv[2]
items = {"dotenv": ".env"}
for name in ("llm_api_key", "tts_api_key", "google_client_secret"):
    items[name] = f"secrets/{name}.txt"
for name, path in items.items():
    value = open(path, encoding="utf-8").read().strip() if os.path.exists(path) else ""
    if not value:
        continue  # SSM refuses empty values; the server leaves that secret empty
    request = {"Name": f"{prefix}/{name}", "Value": value, "Type": "SecureString", "Overwrite": True}
    if len(value.encode()) > 4096:
        request["Tier"] = "Advanced"
    target = os.path.join(folder, f"{name}.json")
    with open(os.open(target, os.O_WRONLY | os.O_CREAT, 0o600), "w", encoding="utf-8") as handle:
        json.dump(request, handle)
PY
for request in "$STAGE"/secrets/*.json; do
  aws ssm put-parameter --cli-input-json "file://$request" >/dev/null
  rm -f "$request"
done
echo "Settings and keys stored under $PREFIX."

# 2. The release: git's file list, as the files are now (including uncommitted changes).
git ls-files -z --cached --others --exclude-standard \
  | python3 -c "import os, sys; sys.stdout.write(''.join(p + '\0' for p in sys.stdin.read().split('\0') if p and os.path.isfile(p) and not p.startswith('secrets/') and not p.endswith('.DS_Store')))" \
  > "$STAGE/files"
COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs -czf "$STAGE/release.tgz" --null -T "$STAGE/files"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
aws s3 cp --only-show-errors "$STAGE/release.tgz" "s3://$BUCKET/releases/$STAMP.tgz"
aws s3 cp --only-show-errors "$STAGE/release.tgz" "s3://$BUCKET/releases/current.tgz"
echo "Release $STAMP uploaded ($(du -h "$STAGE/release.tgz" | cut -f1))."

# Optional: this Mac's database and stored files.
REMOTE=/opt/demo/deploy.sh
if [ "$WITH_DATA" = yes ]; then
  mkdir -p "$STAGE/data/objects"
  docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$STAGE/data/db.dump"
  # The local object store's keys, for this one command only (read from .env, never printed).
  (
    set -a
    # shellcheck source=/dev/null
    . ./.env
    set +a
    AWS_ACCESS_KEY_ID="$S3_ACCESS_KEY" AWS_SECRET_ACCESS_KEY="$S3_SECRET_KEY" AWS_DEFAULT_REGION=us-east-1 \
      aws --endpoint-url "http://localhost:${VOICE_HOST_S3_PORT:-9010}" s3 sync --only-show-errors \
      "s3://${S3_BUCKET:-podcast-episodes}" "$STAGE/data/objects"
  )
  COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs -czf "$STAGE/data.tgz" -C "$STAGE/data" db.dump objects
  aws s3 cp --only-show-errors --sse AES256 "$STAGE/data.tgz" "s3://$BUCKET/data/current.tgz"
  echo "Data copy uploaded ($(du -h "$STAGE/data.tgz" | cut -f1)): database and $(find "$STAGE/data/objects" -type f | wc -l | tr -d ' ') files."
  REMOTE="/opt/demo/deploy.sh restore"
fi

# 3. Install it on the server. The first deploy builds every image there (CUDA PyTorch is large).
COMMAND=$(aws ssm send-command --instance-ids "$INSTANCE" --document-name AWS-RunShellScript \
  --comment "deploy $STAMP" --timeout-seconds 600 \
  --parameters "{\"commands\":[\"$REMOTE\"],\"executionTimeout\":[\"7200\"]}" \
  --query Command.CommandId --output text)
echo "Deploying on $INSTANCE (command $COMMAND); the first one takes 20-40 minutes..."
for _ in $(seq 1 480); do
  sleep 15
  STATUS=$(aws ssm get-command-invocation --command-id "$COMMAND" --instance-id "$INSTANCE" \
    --query Status --output text 2>/dev/null || echo Pending)
  case "$STATUS" in Pending|InProgress|Delayed) ;; *) break ;; esac
done
aws ssm get-command-invocation --command-id "$COMMAND" --instance-id "$INSTANCE" \
  --query '[Status, StandardOutputContent, StandardErrorContent]' --output text | tail -25
echo "Web app: $(out site_url)"
echo "Sign in with Google needs this redirect URI on the OAuth client: $(out google_redirect_uri)"
