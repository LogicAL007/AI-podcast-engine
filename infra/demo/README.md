# The engine on AWS, for a live demo

One GPU server (g4dn.xlarge: an NVIDIA T4, 4 vCPUs, 16 GB of memory) runs the same Docker Compose
stack as the Mac. The voice worker uses the GPU, with Chatterbox and the cloned voices, and Caddy
serves the web app over HTTPS. The server runs in ca-central-1 and is managed through AWS Systems
Manager (SSM), with no SSH.

| Piece | Where |
|---|---|
| Server, IP, firewall (80 and 443 only), role, private bucket | `main.tf` (Terraform) |
| First boot: Docker, GPU runtime, the server's deploy script | `user_data.sh.tftpl` |
| GPU voice worker, Caddy, nothing else published | `docker-compose.aws.yml`, `Caddyfile` |
| Shipping code, settings and (optionally) data from the Mac | `deploy.sh` |
| What `podcast-user` may do (study and demo, one inline policy) | `deployer-policy.json` |
| GitHub's sign-in to AWS for CD: the OIDC provider and a deploy role for this one server | `github.tf` |
| CI checks on every push; CD after CI passes on main | `.github/workflows/ci.yml`, `deploy-demo.yml` |

## Cost (on-demand prices, ca-central-1, approximate)

| State | About |
|---|---|
| Running | $0.58 an hour for the server, plus about $0.02 for the disk and IP |
| Stopped (`make aws-demo-stop`) | $0.50 a day: the 120 GB disk and the IP |
| Destroyed (`make aws-demo-destroy`) | nothing |

A rehearsal day (the first build takes 20–40 minutes), a stop, and a 3-hour demo day come to
about $10.

## Once

1. **GPU quota.** New AWS accounts often have 0 vCPUs for G instances. In the AWS console go to
   Service Quotas → Amazon EC2, region Canada (Central), and open "Running On-Demand G and VT
   instances". The value must be at least 4. If it isn't, request 4 (or 8). Approval can take
   from minutes to a few days. After step 2, `make aws-demo-quota` shows the value.
2. **Permissions for `podcast-user`.** It deploys both the study and the demo, and a user's inline
   policies share 2,048 characters. So it has one inline policy, `deployer-policy.json` (951
   characters), covering both: EC2, SSM commands, snapshots and quotas in ca-central-1, plus
   buckets, roles and settings named `podcast-*`. In IAM → Users → `podcast-user` → Permissions,
   edit its existing inline policy → JSON, replace everything with this file, and save. Check
   with `make aws-demo-whoami`.
3. **Rotate the keys first.** The Gemini key and the Google client secret go to the server, so
   rotate them before the demo if they were ever shared. Put the new values in
   `secrets/*.txt`.

## Bring it up

```sh
make aws-demo-up      # Terraform shows the plan (17 resources) and asks before creating anything
make aws-demo-data    # code, settings and this Mac's data (accounts, shows, episodes, voices)
```

`aws-demo-data` copies the local database and stored files. For it, the local stack must be
running (`make voice-host` publishes the ports it reads). For a later code-only update, run
`make aws-demo-deploy`. Running `make aws-demo-data` again replaces the server's data.

Each deploy prints the site address, `https://<ip-with-dashes>.sslip.io`, and the redirect URI
for Sign in with Google. Add that URI in Google Cloud → APIs & Services → Credentials → the
OAuth client → Authorised redirect URIs. Password sign-in works without it.

## Between rehearsal and demo

```sh
make aws-demo-stop    # after the rehearsal
make aws-demo-start   # on demo day, 10 minutes before; the stack starts by itself
make aws-demo-destroy # after the demo: removes the server, disk, bucket and role
```

The IP stays the same across stop and start, so the address and the Google redirect URI do too.

## CI/CD

```
push or pull request ──> CI (ci.yml)
                         python: ruff, mypy, unit tests
                         web: build
                         docker: compose files (base + AWS overlay), hadolint
                         infra: terraform fmt and validate, shellcheck of the deploy scripts
                              │
              CI passes on main
                              ▼
                         Deploy demo (deploy-demo.yml), in the GitHub `demo` environment
                         1. Sign in to AWS through OIDC: a 2-hour session, no stored keys
                         2. Is the server running? If not, stop here (a notice, not a failure)
                         3. git archive of the commit -> s3://<bucket>/releases/
                         4. SSM runs /opt/demo/deploy.sh on the server: rebuild, restart
                         5. Smoke test: https://<site>/api/ready must answer 200
```

Run it by hand in Actions → Deploy demo → Run workflow, with `deploy`, `start` (start the
server and check it answers) or `stop`.

**What CD does not do:**
- **Data:** it never copies data. That stays `make aws-demo-data`, from the Mac.
- **Settings and keys:** it never touches them. The server reads them from SSM, where
  `deploy.sh` put them. So run `make aws-demo-data` (or `aws-demo-deploy`) once before CD can
  deploy.
- **Unpushed changes:** it deploys only committed code. To ship uncommitted work, use
  `make aws-demo-deploy`.

### Set up once

After `make aws-demo-up`:

1. In GitHub → Settings → Environments, create an environment named **`demo`**. You can add
   yourself as a required reviewer, so every deploy waits for your click.
2. Run `make aws-demo-ci-vars`, and add the five variables it prints to that environment
   (Environment variables, not secrets: none of them is secret).
3. Push to main. After CI passes, the deploy runs if the server is up.

The deploy role can only upload releases, run the deploy script on this one server, and start
or stop it. The `sub` condition in `github.tf` lets only jobs of this repository's `demo`
environment use it. If the account already has a GitHub OIDC provider, Terraform's apply fails
with "EntityAlreadyExists". Then pass its ARN:
`terraform -chdir=infra/demo apply -var github_oidc_provider_arn=arn:aws:iam::<account>:oidc-provider/token.actions.githubusercontent.com`.

## Things to know

- **The Gemini key and its quota are shared with the Mac.** Both stacks count against the same
  Google limits, so leave a day's quota for the demo.
- **Voicing on the T4 is faster than on the Mac**, but a 2-minute episode still takes several
  minutes. For the demo, start an episode early, show the pipeline running, and play one that is
  already published.
- **Vault starts fresh on the server**, with its own unseal key and root token, in
  `/opt/demo/secrets` on the server. Those never leave it, and they are deleted with it. After
  the data copy, users sign in again.
- **Secrets travel only as SSM SecureString parameters**: `.env` and the `secrets/*.txt` keys,
  under `/podcast-demo/`. The release archive is git's file list, so it never contains `secrets/`
  or `research/`.
