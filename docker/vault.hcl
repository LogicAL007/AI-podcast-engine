# Vault for the local stack: one node, data in the `vaultdata` volume, initialised and unsealed by
# the vault-init service (podcast_engine.common.vault_init).

storage "file" {
  path = "/vault/file"
}

# TLS with a certificate from the stack's own CA (vault-certs). Clients verify it against
# secrets/vault-ca.pem; nothing trusts it by accident.
listener "tcp" {
  address         = "0.0.0.0:8200"
  tls_cert_file   = "/vault/tls/vault-cert.pem"
  tls_key_file    = "/vault/tls/vault-key.pem"
  tls_min_version = "tls12"
}

api_addr = "https://vault:8200"
ui       = true

# The containers drop all capabilities, so Vault cannot lock its memory; the host's swap is the
# risk this leaves (Docker Desktop's VM has its own, unencrypted, swap).
disable_mlock = true

default_lease_ttl = "768h"
max_lease_ttl     = "8760h"
