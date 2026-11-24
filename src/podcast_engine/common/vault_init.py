import argparse
import contextlib
import json
import os
import secrets
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from podcast_engine.common.config import VAULT_SECRETS
from podcast_engine.common.vault import KV_MOUNT, VaultError, read_kv, request, write_kv

DESCRIPTION = """Set up the local Vault (the vault-init service), or store one secret.

Run at every docker compose up and safe to repeat: initialise and unseal Vault, enable the KV v2
engine and the app's read-only policy, fill in any secret Vault lacks, and issue a fresh app token.

  python -m podcast_engine.common.vault_init set llm_api_key   (reads the value from stdin)
  docker compose run --rm -T vault-init set llm_api_key < secrets/llm_api_key.txt

Nothing secret is printed.
"""
POLICY = "podcast-app"
APP_TOKEN_TTL = "8760h"  # noqa: S105 - a duration, not a secret. One year; the server's max_lease_ttl allows it (docker/vault.hcl)


def _say(event: str, **fields: Any) -> None:
    """Print one JSON log line; a one-shot job's log.

    Args:
        event: What happened.
        **fields: Details to log with it; never a secret.
    """
    print(json.dumps({"event": event, **fields}), flush=True)  # noqa: T201 - a one-shot job's log


def _write_private(path: Path, text: str) -> None:
    """Write a file readable only by its owner.

    Args:
        path: Where to write.
        text: The file's contents.
    """
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)


def wait_for_vault(addr: str, attempts: int = 60) -> None:
    """Wait until Vault answers.

    Args:
        addr: Vault's address.
        attempts: How many one-second tries to make.

    Raises:
        VaultError: Vault did not answer in time.
    """
    for _ in range(attempts):
        try:
            request(addr, "GET", "sys/seal-status")
            return
        except VaultError:
            time.sleep(1)
    raise VaultError(f"Vault at {addr} did not answer")


def initialise(addr: str, init_file: Path) -> dict[str, Any]:
    """Return Vault's init record, initialising Vault if it is new.

    This is a single-machine deployment, so there is one unseal key. The unseal key and root token
    are kept in ``<secrets>/vault-init.json``, readable only by its owner.

    Args:
        addr: Vault's address.
        init_file: Where the init record is kept.

    Returns:
        The init record: the unseal key and the root token.

    Raises:
        VaultError: Vault is initialised but its init record is missing, so its data cannot be
            unsealed.
    """
    if not request(addr, "GET", "sys/init")["initialized"]:
        record = request(addr, "PUT", "sys/init", body={"secret_shares": 1, "secret_threshold": 1})
        _write_private(init_file, json.dumps(record, indent=2))
        _say("vault_initialised", init_file=str(init_file))
        return record
    if not init_file.exists():
        raise VaultError(
            f"Vault is already initialised but {init_file} is missing: without its unseal key the "
            "data cannot be read. Restore the file, or delete the vault volume to start over."
        )
    loaded: dict[str, Any] = json.loads(init_file.read_text(encoding="utf-8"))
    return loaded


def unseal(addr: str, record: dict[str, Any]) -> None:
    """Unseal Vault if it is sealed; it starts sealed after every restart.

    Args:
        addr: Vault's address.
        record: The init record holding the unseal key.
    """
    if request(addr, "GET", "sys/seal-status")["sealed"]:
        request(addr, "PUT", "sys/unseal", body={"key": record["keys_base64"][0]})
        _say("vault_unsealed")


def configure(addr: str, root: str, kv_path: str) -> None:
    """Enable the KV v2 engine at ``secret/`` and the app's read-only policy.

    Args:
        addr: Vault's address.
        root: The root token.
        kv_path: The path of the app's secrets under ``secret/``.
    """
    mounts = request(addr, "GET", "sys/mounts", token=root)
    if f"{KV_MOUNT}/" not in mounts.get("data", mounts):
        request(
            addr, "POST", f"sys/mounts/{KV_MOUNT}", token=root,
            body={"type": "kv", "options": {"version": "2"}},
        )  # fmt: skip
        _say("kv_enabled", mount=KV_MOUNT)
    policy = f'path "{KV_MOUNT}/data/{kv_path}" {{\n  capabilities = ["read"]\n}}\n'
    request(addr, "PUT", f"sys/policies/acl/{POLICY}", token=root, body={"policy": policy})


def current(addr: str, root: str, kv_path: str) -> dict[str, str]:
    """Read the app's secrets as Vault has them.

    Args:
        addr: Vault's address.
        root: The root token.
        kv_path: The path of the app's secrets.

    Returns:
        The stored secrets; empty when there are none yet.

    Raises:
        VaultError: Vault refused the read for another reason.
    """
    try:
        return read_kv(addr, root, kv_path)
    except VaultError as error:
        if "HTTP 404" in str(error):
            return {}
        raise


def seed(addr: str, root: str, kv_path: str, secrets_dir: Path) -> None:
    """Add the secrets Vault lacks; never overwrite one it has.

    Each missing secret is read from ``<secrets>/<name>.txt`` when that file is non-empty; a missing
    login-token HMAC key is generated. Values already in Vault are changed only with ``set`` or
    Vault's UI. Only the names of secrets added or still missing are logged.

    Args:
        addr: Vault's address.
        root: The root token.
        kv_path: The path of the app's secrets.
        secrets_dir: The folder holding the secret files.
    """
    stored = current(addr, root, kv_path)
    added = []
    for name in VAULT_SECRETS:
        if stored.get(name):
            continue
        source = secrets_dir / f"{name}.txt"
        value = source.read_text(encoding="utf-8").strip() if source.exists() else ""
        if not value and name == "auth_token_key":
            value = secrets.token_urlsafe(48)
        if value:
            stored[name] = value
            added.append(name)
    if added:
        write_kv(addr, root, kv_path, stored)
    missing = [n for n in VAULT_SECRETS if not stored.get(n)]
    _say("secrets_seeded", added=added, missing=missing)


def issue_app_token(addr: str, root: str, token_file: Path) -> None:
    """Issue a fresh read-only token for the services, revoking the previous one.

    A previous token that has already expired or been revoked is ignored. The token lasts a year.

    Args:
        addr: Vault's address.
        root: The root token.
        token_file: Where the services read the token from.
    """
    if token_file.exists() and (old := token_file.read_text(encoding="utf-8").strip()):
        with contextlib.suppress(VaultError):
            request(addr, "POST", "auth/token/revoke", token=root, body={"token": old})
    reply = request(
        addr, "POST", "auth/token/create-orphan", token=root,
        body={"policies": [POLICY], "ttl": APP_TOKEN_TTL, "display_name": "podcast-app",
              "renewable": True},
    )  # fmt: skip
    _write_private(token_file, reply["auth"]["client_token"])
    _say("app_token_issued", ttl=APP_TOKEN_TTL, token_file=str(token_file))


def main(argv: Sequence[str] | None = None) -> int:
    """Set up the local Vault or store a secret: ``python -m podcast_engine.common.vault_init``.

    The ``vault-init`` service runs it at every ``docker compose up``, and it is safe to repeat: it
    initialises and unseals Vault, enables the KV engine and policy, seeds missing secrets and
    issues a fresh app token. ``set <name>`` stores one secret read from stdin; only its name is
    logged, never the value.

    For production, use Vault's own unseal (several key shares, or auto-unseal) and an auth method
    such as AppRole instead of a stored root token.

    Args:
        argv: ``setup`` (the default) or ``set <name>``; the process's own arguments when None.

    Returns:
        0, the process's exit status.
    """
    parser = argparse.ArgumentParser(
        description=DESCRIPTION, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("command", nargs="?", choices=["setup", "set"], default="setup")
    parser.add_argument("name", nargs="?", choices=VAULT_SECRETS, help="for `set`: which secret")
    args = parser.parse_args(argv)
    addr = os.environ.get("VAULT_ADDR", "http://vault:8200")
    secrets_dir = Path(os.environ.get("SECRETS_DIR", "/secrets"))
    kv_path = os.environ.get("VAULT_KV_PATH", "podcast")
    init_file = secrets_dir / "vault-init.json"

    wait_for_vault(addr)
    record = initialise(addr, init_file)
    unseal(addr, record)
    root = record["root_token"]
    configure(addr, root, kv_path)
    if args.command == "set":
        if args.name is None:
            parser.error("set needs the secret's name")
        value = sys.stdin.read().strip()
        if not value:
            parser.error("pipe the value in on stdin")
        stored = current(addr, root, kv_path)
        stored[args.name] = value
        write_kv(addr, root, kv_path, stored)
        _say("secret_set", name=args.name)
        return 0
    seed(addr, root, kv_path, secrets_dir)
    issue_app_token(addr, root, secrets_dir / "vault_app_token.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
