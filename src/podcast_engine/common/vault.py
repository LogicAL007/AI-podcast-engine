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
    """Build the TLS context for talking to Vault.

    Verifies Vault's certificate against our own CA when one is given, else the system's.

    Args:
        ca_file: Vault's CA certificate; the ``VAULT_CACERT`` file, else the system's CAs, when
            None.

    Returns:
        A verifying SSL context.
    """
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
    """Make one call to Vault's HTTP API, at ``{addr}/v1/{path}``.

    Uses only the standard library, so no image needs an extra package. urllib wraps TLS failures in
    ``URLError``; they are reported as a failed verification.

    Args:
        addr: Vault's address (``VAULT_ADDR``), an http(s) URL.
        method: The HTTP method.
        path: The API path after ``/v1/``.
        token: The Vault token to send, or empty for none.
        body: The JSON body to send, or None.
        ca_file: Vault's CA certificate; the ``VAULT_CACERT`` file, else the system's CAs, when
            None.

    Returns:
        The decoded JSON reply; empty for a 204.

    Raises:
        VaultError: The address is not an http(s) URL, Vault is unreachable, TLS verification
            failed, or Vault answered with an error.
    """
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
    except urllib.error.URLError as error:
        if isinstance(error.reason, ssl.SSLError):
            message = f"Vault at {addr}: TLS verification failed ({error.reason})"
            raise VaultError(message) from error
        raise VaultError(f"Vault at {addr} is unreachable: {error.reason}") from error
    result: dict[str, Any] = json.loads(text) if text.strip() else {}
    return result


def read_kv(
    addr: str, token: str, path: str, *, ca_file: str | os.PathLike[str] | None = None
) -> dict[str, str]:
    """Read the latest version of a KV v2 secret.

    Every container reads its secrets once, at start, from Vault's KV version 2 engine. Setting up
    Vault itself (initialise, unseal, policies) is in ``vault_init``.

    Args:
        addr: Vault's address.
        token: A token allowed to read the secret.
        path: The secret's path under the ``secret`` mount.
        ca_file: Vault's CA certificate; the ``VAULT_CACERT`` file, else the system's CAs, when
            None.

    Returns:
        The secret's keys and values; empty when it has none.

    Raises:
        VaultError: Vault could not be reached, refused the token, or has no such secret.
    """
    reply = request(addr, "GET", f"{KV_MOUNT}/data/{path}", token=token, ca_file=ca_file)
    data: dict[str, str] = reply.get("data", {}).get("data") or {}
    return data


def write_kv(addr: str, token: str, path: str, values: dict[str, str]) -> None:
    """Write a new version of a KV v2 secret, replacing all its keys.

    Args:
        addr: Vault's address.
        token: A token allowed to write the secret.
        path: The secret's path under the ``secret`` mount.
        values: Every key and value the secret should hold.

    Raises:
        VaultError: Vault could not be reached or refused the write.
    """
    request(addr, "POST", f"{KV_MOUNT}/data/{path}", token=token, body={"data": values})
