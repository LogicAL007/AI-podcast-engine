"""A minimal client for HashiCorp Vault's HTTP API, using only the standard library.

Every container reads its secrets once, at start, from Vault's KV version 2 engine. This needs no
extra package in any image. Setting up Vault itself (initialise, unseal, policies) is in
``vault_init``.
"""

import json
import os
import ssl
import urllib.error
import urllib.request
from typing import Any

KV_MOUNT = "secret"
TIMEOUT_S = 10


class VaultError(RuntimeError):
    """Vault could not be reached, refused the token, or has no such secret."""


def _tls_context(ca_file: str | os.PathLike[str] | None) -> ssl.SSLContext:
    """Verify Vault's certificate against our own CA (VAULT_CACERT), else the system's."""
    cafile = ca_file or os.environ.get("VAULT_CACERT") or None
    return ssl.create_default_context(cafile=str(cafile) if cafile else None)


def request(
    addr: str,
    method: str,
    path: str,
    *,
    token: str = "",
    body: dict[str, Any] | None = None,
    ca_file: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """One call to ``{addr}/v1/{path}``; returns the decoded JSON body (empty for 204)."""
    url = f"{addr.rstrip('/')}/v1/{path.lstrip('/')}"
    if not url.startswith(("http://", "https://")):
        raise VaultError(f"VAULT_ADDR must be an http(s) URL, not {addr!r}")
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Vault-Token"] = token
    req = urllib.request.Request(url, data=data, method=method, headers=headers)  # noqa: S310
    try:
        context = _tls_context(ca_file) if url.startswith("https://") else None
        with urllib.request.urlopen(req, timeout=TIMEOUT_S, context=context) as reply:  # noqa: S310
            text = reply.read().decode()
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")[:300]
        raise VaultError(f"Vault {method} {path}: HTTP {error.code} {detail}") from error
    except urllib.error.URLError as error:  # urllib wraps TLS failures in URLError
        if isinstance(error.reason, ssl.SSLError):
            message = f"Vault at {addr}: TLS verification failed ({error.reason})"
            raise VaultError(message) from error
        raise VaultError(f"Vault at {addr} is unreachable: {error.reason}") from error
    result: dict[str, Any] = json.loads(text) if text.strip() else {}
    return result


def read_kv(
    addr: str, token: str, path: str, *, ca_file: str | os.PathLike[str] | None = None
) -> dict[str, str]:
    """The latest version of a KV v2 secret, as a dict of its keys."""
    reply = request(addr, "GET", f"{KV_MOUNT}/data/{path}", token=token, ca_file=ca_file)
    data: dict[str, str] = reply.get("data", {}).get("data") or {}
    return data


def write_kv(addr: str, token: str, path: str, values: dict[str, str]) -> None:
    """Write a new version of a KV v2 secret (replacing all its keys)."""
    request(addr, "POST", f"{KV_MOUNT}/data/{path}", token=token, body={"data": values})
