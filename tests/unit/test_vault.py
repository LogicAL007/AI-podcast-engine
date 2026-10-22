"""Vault: settings read secrets from it, and vault_init sets it up. Against an in-process fake of
the few HTTP endpoints used (the real Vault is exercised by the compose stack)."""

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from podcast_engine.common import vault_init
from podcast_engine.common.config import Settings
from podcast_engine.common.vault import VaultError, read_kv

ROOT_TOKEN = "root-token"


class FakeVault:
    def __init__(self) -> None:
        self.initialized = False
        self.sealed = True
        self.mounts: dict[str, Any] = {"sys/": {}}
        self.kv: dict[str, dict[str, str]] = {}
        self.tokens: dict[str, list[str]] = {ROOT_TOKEN: ["root"]}
        self.revoked: list[str] = []
        self.policies: dict[str, str] = {}
        self.issued = 0

    def handle(self, method: str, path: str, token: str, body: dict[str, Any]) -> tuple[int, Any]:
        if path == "sys/seal-status":
            return 200, {"sealed": self.sealed, "initialized": self.initialized}
        if path == "sys/init":
            if method == "GET":
                return 200, {"initialized": self.initialized}
            self.initialized = True
            return 200, {"keys_base64": ["unseal-key"], "root_token": ROOT_TOKEN}
        if path == "sys/unseal":
            if body.get("key") != "unseal-key":
                return 400, {"errors": ["bad key"]}
            self.sealed = False
            return 200, {"sealed": False}
        if self.sealed:
            return 503, {"errors": ["Vault is sealed"]}
        policies = self.tokens.get(token)
        if policies is None:
            return 403, {"errors": ["permission denied"]}
        if path.startswith("secret/data/"):
            name = path.removeprefix("secret/data/")
            if method == "GET":
                if "root" not in policies and "podcast-app" not in policies:
                    return 403, {"errors": ["permission denied"]}
                if name not in self.kv:
                    return 404, {"errors": []}
                return 200, {"data": {"data": self.kv[name]}}
            if "root" not in policies:
                return 403, {"errors": ["permission denied"]}
            self.kv[name] = body["data"]
            return 200, {}
        if "root" not in policies:
            return 403, {"errors": ["permission denied"]}
        if path == "sys/mounts":
            return 200, {"data": self.mounts}
        if path.startswith("sys/mounts/"):
            self.mounts[path.removeprefix("sys/mounts/") + "/"] = body
            return 204, None
        if path.startswith("sys/policies/acl/"):
            self.policies[path.removeprefix("sys/policies/acl/")] = body["policy"]
            return 204, None
        if path == "auth/token/create-orphan":
            self.issued += 1
            new = f"app-token-{self.issued}"
            self.tokens[new] = body["policies"]
            return 200, {"auth": {"client_token": new}}
        if path == "auth/token/revoke":
            self.tokens.pop(body["token"], None)
            self.revoked.append(body["token"])
            return 204, None
        return 404, {"errors": [f"unknown path {path}"]}


@pytest.fixture
def vault() -> Iterator[tuple[FakeVault, str]]:
    fake = FakeVault()

    class Handler(BaseHTTPRequestHandler):
        def _serve(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length)) if length else {}
            code, payload = fake.handle(
                self.command,
                self.path.removeprefix("/v1/"),
                self.headers.get("X-Vault-Token", ""),
                body,
            )
            self.send_response(code)
            self.end_headers()
            if payload is not None:
                self.wfile.write(json.dumps(payload).encode())

        do_GET = do_PUT = do_POST = _serve  # noqa: N815

        def log_message(self, *args: Any) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield fake, f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def _run_init(monkeypatch: pytest.MonkeyPatch, addr: str, secrets_dir: Path, *args: str) -> int:
    monkeypatch.setenv("VAULT_ADDR", addr)
    monkeypatch.setenv("SECRETS_DIR", str(secrets_dir))
    return vault_init.main(list(args))


def test_setup_initialises_unseals_seeds_and_issues_a_read_only_token(
    vault: tuple[FakeVault, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake, addr = vault
    (tmp_path / "llm_api_key.txt").write_text("sk-from-file\n")
    assert _run_init(monkeypatch, addr, tmp_path) == 0

    assert fake.initialized
    assert not fake.sealed
    record = json.loads((tmp_path / "vault-init.json").read_text())
    assert record["root_token"] == ROOT_TOKEN
    assert oct((tmp_path / "vault-init.json").stat().st_mode)[-3:] == "600"
    stored = fake.kv["podcast"]
    assert stored["llm_api_key"] == "sk-from-file"
    assert len(stored["auth_token_key"]) >= 48  # generated
    assert "tts_api_key" not in stored  # nothing to seed from
    assert 'capabilities = ["read"]' in fake.policies["podcast-app"]
    app_token = (tmp_path / "vault_app_token.txt").read_text()
    assert fake.tokens[app_token] == ["podcast-app"]


def test_a_second_run_unseals_keeps_secrets_and_rotates_the_app_token(
    vault: tuple[FakeVault, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake, addr = vault
    _run_init(monkeypatch, addr, tmp_path)
    first_key = fake.kv["podcast"]["auth_token_key"]
    first_token = (tmp_path / "vault_app_token.txt").read_text()
    fake.sealed = True  # as after a restart
    (tmp_path / "llm_api_key.txt").write_text("a different key")  # files only seed

    _run_init(monkeypatch, addr, tmp_path)
    assert not fake.sealed
    assert fake.kv["podcast"]["auth_token_key"] == first_key
    assert fake.kv["podcast"]["llm_api_key"] == "a different key"  # was missing, so seeded now
    assert first_token in fake.revoked
    assert (tmp_path / "vault_app_token.txt").read_text() != first_token


def test_set_replaces_one_secret_from_stdin(
    vault: tuple[FakeVault, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake, addr = vault
    _run_init(monkeypatch, addr, tmp_path)
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("new-gemini-key\n"))
    assert _run_init(monkeypatch, addr, tmp_path, "set", "llm_api_key") == 0
    assert fake.kv["podcast"]["llm_api_key"] == "new-gemini-key"
    assert "new-gemini-key" not in capsys.readouterr().out  # never printed


def test_initialised_vault_without_its_record_is_a_clear_error(
    vault: tuple[FakeVault, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake, addr = vault
    fake.initialized = True
    with pytest.raises(VaultError, match=r"vault-init\.json is missing"):
        _run_init(monkeypatch, addr, tmp_path)


def test_settings_read_secrets_from_vault_over_files(
    vault: tuple[FakeVault, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake, addr = vault
    _run_init(monkeypatch, addr, tmp_path)
    fake.kv["podcast"]["llm_api_key"] = "from-vault"
    file_key = tmp_path / "llm.txt"
    file_key.write_text("from-file")
    settings = Settings(
        _env_file=None,
        vault_addr=addr,
        vault_token_file=tmp_path / "vault_app_token.txt",
        llm_api_key_file=file_key,
    )
    assert settings.llm_api_key.get_secret_value() == "from-vault"
    assert settings.auth_token_key.get_secret_value() == fake.kv["podcast"]["auth_token_key"]


def test_a_revoked_token_cannot_read(
    vault: tuple[FakeVault, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, addr = vault
    _run_init(monkeypatch, addr, tmp_path)
    with pytest.raises(VaultError, match="403"):
        read_kv(addr, "not-a-token", "podcast")
