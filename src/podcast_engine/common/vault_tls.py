"""TLS for the local Vault: ``python -m podcast_engine.common.vault_tls`` (the vault-certs service).

Run at every ``docker compose up``, before Vault starts, and safe to repeat:

* A private certificate authority is created once. Its key stays in ``<secrets>/vault-ca-key.pem``
  (owner-only); its certificate, ``<secrets>/vault-ca.pem``, is what every client trusts.
* Vault's server certificate (names ``vault``, ``localhost`` and ``127.0.0.1``, valid one year)
  is issued into the ``vaulttls`` volume, owned by Vault's user with the key readable only by it.
  It is replaced when it is within 30 days of expiry, or when its names change.

From the host: ``curl --cacert secrets/vault-ca.pem https://localhost:8200/v1/sys/health``.
For production, use a certificate from your organisation's CA instead.
"""

import ipaddress
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

DNS_NAMES = ("vault", "localhost")
IP_NAMES = ("127.0.0.1",)
CA_YEARS = 10
SERVER_DAYS = 365
RENEW_WITHIN = timedelta(days=30)
VAULT_UID, VAULT_GID = 100, 1000  # the vault user in hashicorp/vault


def _say(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, default=str), flush=True)  # noqa: T201


def _write(path: Path, data: bytes, mode: int, owner: tuple[int, int] | None = None) -> None:
    path.unlink(missing_ok=True)  # replace, even a read-only file
    path.write_bytes(data)
    path.chmod(mode)
    if owner is not None and os.geteuid() == 0:
        os.chown(path, *owner)


def _pem_key(key: ec.EllipticCurvePrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )


def ensure_ca(
    secrets_dir: Path, now: datetime
) -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey]:
    cert_path, key_path = secrets_dir / "vault-ca.pem", secrets_dir / "vault-ca-key.pem"
    if (
        cert_path.exists()
        and key_path.exists()
        and cert_path.stat().st_size
        and key_path.stat().st_size
    ):
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        if (
            isinstance(key, ec.EllipticCurvePrivateKey)
            and cert.not_valid_after_utc > now + RENEW_WITHIN
        ):
            return cert, key
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Podcast Engine local CA")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=365 * CA_YEARS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_cert_sign=True,
                crl_sign=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    _write(key_path, _pem_key(key), 0o600)
    _write(cert_path, cert.public_bytes(serialization.Encoding.PEM), 0o644)
    _say("ca_created", expires=cert.not_valid_after_utc)
    return cert, key


def needs_server_cert(path: Path, ca: x509.Certificate, now: datetime) -> bool:
    if not path.exists() or not path.stat().st_size:
        return True
    cert = x509.load_pem_x509_certificate(path.read_bytes())
    if cert.issuer != ca.subject or cert.not_valid_after_utc <= now + RENEW_WITHIN:
        return True
    names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    return set(names.get_values_for_type(x509.DNSName)) != set(DNS_NAMES) or {
        str(ip) for ip in names.get_values_for_type(x509.IPAddress)
    } != set(IP_NAMES)


def issue_server_cert(
    tls_dir: Path, ca: x509.Certificate, ca_key: ec.EllipticCurvePrivateKey, now: datetime
) -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    alt_names: list[x509.GeneralName] = [x509.DNSName(name) for name in DNS_NAMES]
    alt_names += [x509.IPAddress(ipaddress.ip_address(ip)) for ip in IP_NAMES]
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "vault")]))
        .issuer_name(ca.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=SERVER_DAYS))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName(alt_names), critical=False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )
    owner = (VAULT_UID, VAULT_GID)
    _write(tls_dir / "vault-key.pem", _pem_key(key), 0o400, owner)
    _write(tls_dir / "vault-cert.pem", cert.public_bytes(serialization.Encoding.PEM), 0o444, owner)
    _say("server_cert_issued", names=[*DNS_NAMES, *IP_NAMES], expires=cert.not_valid_after_utc)


def main() -> int:
    secrets_dir = Path(os.environ.get("SECRETS_DIR", "/secrets"))
    tls_dir = Path(os.environ.get("VAULT_TLS_DIR", "/tls"))
    now = datetime.now(UTC)
    ca, ca_key = ensure_ca(secrets_dir, now)
    # The CA certificate also goes next to Vault's own, for its healthcheck's `vault status`.
    _write(tls_dir / "ca.pem", ca.public_bytes(serialization.Encoding.PEM), 0o444)
    if needs_server_cert(tls_dir / "vault-cert.pem", ca, now):
        issue_server_cert(tls_dir, ca, ca_key, now)
    else:
        _say("server_cert_current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
