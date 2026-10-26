"""Diagrams 06 to 14: the API's layers, security, sequences, data, deployment, web app,
evaluation and observability."""

from __future__ import annotations

from svgkit import ACCENT, FAINT, INK, KINDS, MUTED, PANEL, RULE, WHITE, Box, Diagram, text_width

TOTAL = 14


def new(slug: str, number: int, title: str, subtitle: str, **size: int) -> Diagram:
    return Diagram(slug, number, TOTAL, title, subtitle, **size)


# ---- 06 --------------------------------------------------------------------------------------
def api_layers() -> Diagram:
    d = new("06-api-layers", 6, "API: layers and modules",
            "One file per layer and resource; each layer may only call the one below it", h=900)  # fmt: skip
    d.rect(210, 112, 1130, 34, fill="#FFF4EC", stroke=ACCENT, rx=8)
    d.text(226, 134, "nginx /api  →  uvicorn  →  FastAPI app (create_app)  →  metrics middleware  →  "
           "routers under /v1 (discovery and health at the root)", size=12.5, maxw=1100)  # fmt: skip
    bands = [("Routers", "paths, status codes,", "OpenAPI metadata", 170),
             ("Controllers", "call the service, map", "domain errors to HTTP", 290),
             ("Services", "business rules; no", "FastAPI, no SQL", 410),
             ("Repositories", "SQL behind Protocols;", "fakes in unit tests", 530)]  # fmt: skip
    for name, a, b, y in bands:
        d.text(40, y + 34, name, size=14, bold=True)
        d.text(40, y + 54, a, size=11.5, color=MUTED, maxw=160)
        d.text(40, y + 70, b, size=11.5, color=MUTED, maxw=160)
        d.line(40, y + 104, 1340, y + 104, color="#EEEAE6")
    cols = [
        ("auth", "public", ["auth_router", "/v1/auth/*"], ["AuthController", "cookies, mail"],
         ["AuthService", "Argon2, tokens, CSRF"], ["AuthRepository", "events · attempts"]),
        ("shows", "signed in", ["shows_router", "/v1/shows"], ["ShowController"], ["ShowService"],
         ["ShowRepository", "owner-scoped"]),
        ("episodes", "signed in", ["episodes_router", "+ /events (SSE)"], ["EpisodeController", "follow_progress"],
         ["EpisodeService", "lifecycle, edits"], ["EpisodeRepository"]),
        ("sources", "signed in", ["sources_router"], ["SourceController"], ["SourceService"], ["SourceRepository"]),
        ("uploads", "signed in", ["uploads_router", "PDF upload"], ["UploadController"],
         ["UploadService", "size and type"], ["UploadRepository", "+ object store"]),
        ("media, feeds", "public", ["media_router", "feeds_router"], ["Episode, Upload,", "FeedController"],
         ["FeedService"], ["object store", "Range requests"]),
        ("home, ops", "public, root", ["home_router", "ops_router"], ["HomeController", "OpsController"],
         ["HomeService", "OpsService"], ["readiness checks", "DB, queue, storage"]),
    ]  # fmt: skip
    cw, gap = 150, 13
    for i, (name, access, r, c, s, p) in enumerate(cols):
        x = 210 + i * (cw + gap)
        kind = "edge" if access == "signed in" else "plain"
        d.text(x + cw / 2, 164, name, size=12.5, bold=True, anchor="middle")
        for lines, y, k in (
            (r, 182, "service"),
            (c, 302, "service"),
            (s, 422, "service"),
            (p, 542, "store"),
        ):
            d.box(x, y, cw, 82, None, None, lines, kind=k, align="center",
                  line_size=11.5, pad=10)  # fmt: skip
        d.pill(
            x + (cw - text_width(access, 11) - 14) / 2,
            254,
            access,
            kind if kind == "edge" else "note",
        )
    infra = [("PostgreSQL", "store"), ("Redis", "store"), ("Object storage", "store"), ("Vault (keys)", "security"),
             ("SMTP (mail)", "support"), ("Celery queues", "store")]  # fmt: skip
    d.text(40, 682, "Infrastructure", size=14, bold=True)
    for i, (name, kind) in enumerate(infra):
        d.box(
            210 + i * 190,
            660,
            175,
            46,
            name,
            None,
            (),
            kind=kind,
            align="center",
            title_size=12.5,
            pad=13,
        )
    cross = d.box(1360, 112, 200, 594, "Cross-cutting", None, [
        "dependencies.py", "  wiring; get_current_user:", "  bearer, or cookie + CSRF",
        "errors.py", "  domain errors → HTTP", "pagination.py", "  Page {items, total, next}",
        "openapi.py", "  docs, operation ids", "observability.py", "  request metrics",
        "paths.py · cookies.py", "  /v1 · session cookies"], kind="note", line_size=11.5, mono_lines=False)  # fmt: skip
    del cross
    rules = ["Feed, audio, notes and PDF URLs from before /v1 still answer (hidden from the OpenAPI description).",
             "Another user's show, episode or upload answers 404, the same as one that does not exist."]  # fmt: skip
    for i, row in enumerate(rules):
        d.text(48, 748 + i * 20, row, size=12, color=MUTED)
    d.legend(48, 812, ["service", "store", "security", "support"])
    d.pill(560, 798, "signed in", "edge")
    d.text(640, 812, "needs a sign-in", size=11.5, color=MUTED)
    return d


# ---- 07 --------------------------------------------------------------------------------------
def security() -> Diagram:
    d = new("07-security", 7, "Security architecture",
            "Trust zones, how each caller proves who it is, and where secrets and hashes live", h=960)  # fmt: skip
    d.group(40, 125, 250, 545, "Users' devices")
    browser = d.box(55, 165, 220, 150, "Browser", "web app", [
        "Session cookie: HttpOnly,", "SameSite=Strict, 180 days", "Reads pe_csrf; sends it as",
        "X-CSRF-Token on changes"], kind="client")  # fmt: skip
    scripts = d.box(
        55,
        340,
        220,
        110,
        "Scripts, notebooks",
        "API clients",
        ["Bearer pes_ login token", "or pek_ API key"],
        kind="client",
    )
    apps = d.box(
        55,
        475,
        220,
        110,
        "Podcast apps",
        None,
        ["Public GETs only: feed,", "audio, notes, PDFs"],
        kind="client",
    )
    d.group(320, 125, 250, 545, "Edge")
    nginx = d.box(335, 165, 220, 290, "nginx", "the only port open: 8080", [
        "Content-Security-Policy:", "own origin only; no", "framing, no plugins",
        "nosniff; same-origin", "referrer policy", "/api/metrics blocked", "Upload cap 26 MB"], kind="edge")  # fmt: skip
    d.group(600, 125, 540, 545, "Application · internal network")
    api = d.box(615, 165, 510, 330, "API", "FastAPI", [
        "Passwords: Argon2id, at least 12 characters",
        "Tokens: random; only an HMAC-SHA256 is stored,",
        "  keyed from Vault; 180-day expiry; revocable",
        "Cookie requests that change data: CSRF token",
        "  must equal HMAC(key, token id), else 403",
        "Login limits: 5 failures in 15 min lock the account;",
        "  50 from one address answer 429 (Redis counters)",
        "Reset: single-use, 30-minute link; token in #fragment",
        "Ownership: another user's record answers 404",
        "Roles admin and creator; every sign-in, lock, reset,",
        "  key and account change goes to the security log",
    ], line_size=12)  # fmt: skip
    workers = d.box(615, 520, 510, 130, "Stage workers", None, [
        "Read model keys from Vault at start",
        "A cloned voice needs a consent record (config/voices.yaml)",
        "Sources and PDFs are untrusted input: parsed, never run"], kind="worker")  # fmt: skip
    d.group(1170, 125, 390, 300, "Secrets")
    vault = d.box(1185, 165, 360, 240, "Vault 2.1", "HTTPS with the stack's own CA", [
        "KV: llm_api_key, tts_api_key,", "auth_token_key, smtp_password",
        "Services hold a read-only token", "(Docker secret vault_app_token)",
        "vault-certs: issues the TLS certificate", "vault-init: unseals, seeds, issues token"], kind="security")  # fmt: skip
    d.group(1170, 445, 390, 225, "Data")
    pg = d.cylinder(
        1185,
        485,
        170,
        165,
        "PostgreSQL",
        None,
        ["Hashes only:", "tokens, reset", "links, passwords", "owner_id on shows"],
    )
    d.cylinder(1375, 485, 170, 75, "Redis", None, ["Login counters"])
    d.cylinder(1375, 575, 170, 75, "Object storage", None, ["Private bucket"])
    d.arrow([browser.right(0.45), (nginx.x, browser.y + 67)], "cookie, CSRF", at=(305, 220))
    d.arrow([scripts.right(), (nginx.x, scripts.cy)], "Bearer", at=(305, 382))
    d.arrow(
        [apps.right(), (nginx.x + 60, apps.cy), (nginx.x + 60, nginx.b)], "public", at=(305, 518)
    )
    d.arrow([(nginx.r, 300), (api.x, 300)], "/api", at=(585, 288))
    d.arrow([(api.r, 230), (vault.x, 230)], "token key", at=(1155, 218))
    d.arrow([(api.r, 470), (1160, 470), (1160, 520), (pg.x, 520)], "accounts", at=(1150, 455))
    d.arrow([(workers.r, 600), (pg.x, 600)], "state", at=(1155, 588))
    d.rect(40, 700, 1520, 120, fill=PANEL, stroke=RULE, rx=10)
    d.text(58, 726, "Network exposure", size=13, bold=True)
    exposure = [
        ("open to the network", "8080 web (nginx)", "edge"),
        ("this computer only", "8000 API · 8200 Vault · 9001 storage console · 8025 Mailpit · 9090 Prometheus", "note"),
        ("dev override only", "5432 PostgreSQL (127.0.0.1)", "note"),
        ("internal only", "Redis, object storage API, every worker, the scheduler", "note"),
    ]  # fmt: skip
    for i, (tag, what, kind) in enumerate(exposure):
        y = 742 + i * 20
        d.text(
            58,
            y + 11,
            tag,
            size=11.5,
            bold=True,
            color=ACCENT if kind == "edge" else MUTED,
            maxw=160,
        )
        d.text(220, y + 11, what, size=11.5, maxw=1320)
    d.text(48, 852, "Not built yet: HTTPS at nginx, multi-factor sign-in, private feeds, invitations. "
           "Passwords and reset tokens never appear in logs; mail is sent after the response.", size=12, color=MUTED)  # fmt: skip
    return d


# ---- sequences --------------------------------------------------------------------------------
def lifelines(
    d: Diagram, parts: list[tuple[str, str, str, float]], top: float, bottom: float
) -> dict[str, float]:
    xs = {}
    for key, name, kind, x in parts:
        d.box(
            x - 88, top, 176, 52, name, None, (), kind=kind, align="center", title_size=13, pad=17
        )
        d.line(x, top + 52, x, bottom, color=FAINT, dashed=True)
        xs[key] = x
    return xs


def message(d: Diagram, xs: dict[str, float], a: str, b: str, y: float, label: str, *, reply: bool = False,
            wide: bool = False) -> None:  # fmt: skip
    xa, xb = xs[a], xs[b]
    if a == b:
        d.arrow(
            [(xa + 4, y - 8), (xa + 46, y - 8), (xa + 46, y + 8), (xa + 6, y + 8)],
            color=MUTED,
            sw=1.3,
        )
        d.label(xa + 54, y, label, size=11.5, anchor="start")
        return
    sign = 1 if xb > xa else -1
    d.arrow(
        [(xa + sign * 4, y), (xb - sign * 4, y)],
        color=MUTED if reply else INK,
        dashed=reply,
        sw=1.3,
    )
    mid = (xa + xb) / 2
    width = text_width(label, 11.5)
    if not wide and width > abs(xb - xa) - 12:
        d.problems.append(
            f"{d.slug}: message {label!r} ({width:.0f}px) wider than its arrow ({abs(xb - xa):.0f}px)"
        )
    d.label(mid, y - 10, label, size=11.5, color=MUTED if reply else INK)


def sign_in_sequence() -> Diagram:
    d = new("08-sign-in-sequence", 8, "Sequence: browser sign-in, then a change",
            "How the web app signs in without ever seeing the token, and how a change is authorised", h=960)  # fmt: skip
    parts = [("b", "Browser (SPA)", "client", 120), ("n", "nginx", "edge", 330), ("a", "API", "service", 560),
             ("s", "AuthService", "service", 800), ("r", "Redis", "store", 1020), ("p", "PostgreSQL", "store", 1240),
             ("v", "Vault", "security", 1460)]  # fmt: skip
    xs = lifelines(d, parts, 118, 905)
    d.frame(470, 186, 1080, 54, "at start")
    message(
        d,
        xs,
        "a",
        "v",
        222,
        "read auth_token_key (HTTPS, read-only token), kept in memory",
        wide=True,
    )
    d.frame(40, 256, 1520, 330, "sign in")
    y = 300
    message(d, xs, "b", "n", y, "POST /api/v1/auth/browser-session")
    message(d, xs, "n", "a", y + 34, "proxy, client address")
    message(d, xs, "a", "s", y + 68, "login(email, password)")
    message(d, xs, "s", "r", y + 102, "address and account limits")
    message(d, xs, "s", "p", y + 136, "find user; verify Argon2id hash", wide=True)
    message(d, xs, "s", "p", y + 170, "store HMAC-SHA256 of a new token", wide=True)
    message(d, xs, "s", "p", y + 204, "security event: login_succeeded", wide=True)
    message(d, xs, "s", "a", y + 238, "token, its id", reply=True)
    message(
        d,
        xs,
        "a",
        "b",
        y + 272,
        "200 user · Set-Cookie pe_session (HttpOnly) and pe_csrf",
        reply=True,
        wide=True,
    )
    d.frame(40, 602, 1520, 285, "later: a change, such as creating a show")
    y = 646
    message(
        d,
        xs,
        "b",
        "n",
        y,
        "POST /api/v1/shows",
    )
    d.text(xs["b"] + 8, y + 16, "cookie + X-CSRF-Token", size=11, color=MUTED)
    message(d, xs, "n", "a", y + 40, "proxy")
    message(
        d,
        xs,
        "a",
        "p",
        y + 74,
        "get_current_user: find the token by its HMAC; not revoked, not expired",
        wide=True,
    )
    message(d, xs, "a", "a", y + 112, "X-CSRF-Token = HMAC(key, token id)?  If not: 403")
    message(d, xs, "a", "p", y + 150, "insert show, owner_id = the caller", wide=True)
    message(d, xs, "a", "b", y + 188, "201 show", reply=True, wide=True)
    d.text(48, 930 - 0, "", size=1)
    return d


def generation_sequence() -> Diagram:
    d = new("09-generation-sequence", 9, "Sequence: generating an episode",
            "From the Generate button to playing the audio, with live progress over server-sent events", h=1000)  # fmt: skip
    parts = [("b", "Browser", "client", 110), ("a", "API", "service", 330), ("p", "PostgreSQL", "store", 560),
             ("r", "Redis queues", "store", 790), ("w", "Stage workers", "worker", 1020),
             ("s", "Object storage", "store", 1250), ("x", "LLM, speech", "external", 1470)]  # fmt: skip
    xs = lifelines(d, parts, 118, 950)
    y = 205
    message(d, xs, "b", "a", y, "POST /v1/shows/{id}/episodes")
    message(d, xs, "a", "p", y + 32, "insert episode: queued (commit first)", wide=True)
    message(d, xs, "a", "r", y + 64, "enqueue ingest", wide=True)
    message(d, xs, "a", "b", y + 96, "202 episode", reply=True)
    message(d, xs, "b", "a", y + 128, "GET /v1/episodes/{id}/events")
    d.frame(560 - 70, 362, 1070, 236, "loop · each of the 8 stages")
    y = 404
    message(d, xs, "r", "w", y, "stage job")
    message(d, xs, "w", "p", y + 34, "status processing, stage; read inputs", wide=True)
    message(d, xs, "w", "x", y + 68, "prompts; lines to speak")
    message(d, xs, "w", "s", y + 102, "line audio, WAV, notes, feed", wide=True)
    message(d, xs, "w", "p", y + 136, "outputs; stage_runs row", wide=True)
    message(d, xs, "w", "r", y + 170, "enqueue next stage", wide=True)
    d.frame(40, 612, 580, 116, "meanwhile · every second while running")
    y = 652
    message(d, xs, "a", "p", y, "read episode (own short session)", wide=True)
    message(d, xs, "a", "b", y + 34, "event: episode {stage, step}", reply=True, wide=True)
    y = 760
    message(d, xs, "w", "p", y, "status published", wide=True)
    message(
        d, xs, "a", "b", y + 32, "last event, running: false; stream ends", reply=True, wide=True
    )
    message(d, xs, "b", "a", y + 72, "GET …/audio.wav (Range)")
    message(d, xs, "a", "s", y + 104, "get object", wide=True)
    message(d, xs, "a", "b", y + 136, "206 audio bytes", reply=True)
    return d


# ---- 10 --------------------------------------------------------------------------------------
def table(
    d: Diagram, x: float, y: float, name: str, cols: list[tuple[str, str, str]], w: float = 250
) -> Box:
    h = 34 + len(cols) * 19 + 8
    fill, stroke = KINDS["store"]
    d.rect(x, y, w, h, fill=WHITE, stroke=stroke, rx=8, shadow=True)
    d.add(f'<path d="M{x + 0.7},{y + 34} L{x + 0.7},{y + 8} Q{x + 0.7},{y + 0.7} {x + 8},{y + 0.7} '
          f'L{x + w - 8},{y + 0.7} Q{x + w - 0.7},{y + 0.7} {x + w - 0.7},{y + 8} L{x + w - 0.7},{y + 34} Z" '
          f'fill="{fill}"/>')  # fmt: skip
    d.line(x, y + 34, x + w, y + 34, color=stroke, sw=1.2)
    d.text(x + 12, y + 22, name, size=13.5, bold=True, mono=True, maxw=w - 24)
    for i, (key, col, typ) in enumerate(cols):
        cy = y + 34 + 19 * (i + 1) - 4
        if key:
            d.text(x + 12, cy, key, size=9.5, bold=True, color=ACCENT if key == "PK" else "#5B4B8A")
        d.text(x + 38, cy, col, size=11.5, mono=True, maxw=w - 38 - text_width(typ, 10.5) - 18)
        d.text(x + w - 12, cy, typ, size=10.5, color=MUTED, anchor="end")
    return Box(x, y, w, h)


def data_model() -> Diagram:
    d = new("10-data-model", 10, "Data model",
            "PostgreSQL tables and how they relate; a show belongs to one user, and everything else hangs off it",
            h=1000)  # fmt: skip
    users = table(
        d,
        40,
        120,
        "users",
        [
            ("PK", "user_id", "uuid"),
            ("UK", "email", "text"),
            ("", "password_hash", "Argon2id"),
            ("", "role", "admin|creator"),
            ("", "disabled", "bool"),
            ("", "created_at", "time"),
        ],
    )
    tokens = table(
        d,
        40,
        330,
        "auth_tokens",
        [
            ("PK", "token_id", "uuid"),
            ("FK", "user_id", "uuid"),
            ("", "kind", "session|key"),
            ("UK", "token_hash", "HMAC"),
            ("", "prefix", "text"),
            ("", "expires_at", "time"),
            ("", "last_used_at", "time"),
            ("", "revoked_at", "time"),
        ],
    )
    resets = table(
        d,
        40,
        570,
        "password_resets",
        [
            ("PK", "reset_id", "uuid"),
            ("FK", "user_id", "uuid"),
            ("UK", "token_hash", "HMAC"),
            ("", "expires_at", "time"),
            ("", "used_at", "time"),
        ],
    )
    events = table(
        d,
        40,
        760,
        "security_events",
        [
            ("PK", "event_id", "uuid"),
            ("FK", "user_id", "set null"),
            ("", "event", "text"),
            ("", "address", "text"),
            ("", "detail", "jsonb"),
            ("", "created_at", "time"),
        ],
    )
    shows = table(
        d,
        350,
        120,
        "shows",
        [
            ("PK", "show_id", "uuid"),
            ("FK", "owner_id", "uuid"),
            ("", "topic", "text"),
            ("", "tone", "text"),
            ("", "target_minutes", "int"),
            ("", "host_count", "int"),
            ("", "sources", "jsonb"),
            ("", "max_segments", "int"),
            ("", "review_before_voice", "bool"),
        ],
    )
    uploads = table(
        d,
        350,
        420,
        "uploads",
        [
            ("PK", "upload_id", "uuid"),
            ("FK", "show_id", "uuid"),
            ("", "filename", "text"),
            ("", "size_bytes", "bigint"),
            ("", "object_key", "text"),
        ],
    )
    items = table(
        d,
        660,
        120,
        "source_items",
        [
            ("PK", "item_id", "uuid"),
            ("FK", "show_id", "uuid"),
            ("UK", "url", "per show"),
            ("", "title", "text"),
            ("", "content_hash", "sha256"),
            ("", "reliability", "tier"),
            ("", "position", "int"),
        ],
    )
    chunks = table(
        d,
        970,
        120,
        "chunks",
        [
            ("PK", "chunk_id", "uuid"),
            ("FK", "item_id", "uuid"),
            ("UK", "position", "per item"),
            ("", "text", "text"),
            ("", "embedding", "vector(384)"),
        ],
    )
    episodes = table(
        d,
        660,
        370,
        "episodes",
        [
            ("PK", "episode_id", "uuid"),
            ("FK", "show_id", "uuid"),
            ("", "status", "text"),
            ("", "stage", "text"),
            ("", "revision", "int"),
            ("", "rewrite_count", "int"),
            ("", "script", "jsonb"),
            ("", "fact_check", "jsonb"),
            ("", "audio_key", "text"),
            ("", "audio_mp3_key", "text"),
            ("", "notes_key", "text"),
            ("", "approved_at", "time"),
            ("", "published_at", "time"),
        ],
    )
    segments = table(
        d,
        970,
        370,
        "segments",
        [
            ("PK", "segment_id", "uuid"),
            ("FK", "episode_id", "uuid"),
            ("UK", "position", "per ep."),
            ("", "title", "text"),
            ("", "source_item_ids", "uuid[]"),
            ("", "chunk_ids", "uuid[]"),
            ("", "needs_script", "bool"),
        ],
    )
    claims = table(
        d,
        970,
        620,
        "claims",
        [
            ("PK", "claim_id", "uuid"),
            ("FK", "episode_id", "uuid"),
            ("FK", "segment_id", "set null"),
            ("", "text", "text"),
            ("", "chunk_ids", "uuid[]"),
            ("", "supported", "bool"),
            ("", "reason", "text"),
        ],
    )
    runs = table(d, 660, 740, "stage_runs", [("PK", "run_id", "uuid"), ("FK", "episode_id", "uuid"), ("", "stage", "text"),
                                             ("", "model", "text"), ("", "prompt_version", "text"), ("", "seed", "bigint"),
                                             ("", "seconds", "numeric")])  # fmt: skip

    def rel(
        points: list[tuple[float, float]],
        *,
        optional: bool = False,
        label: str | None = None,
        at=None,
    ) -> None:
        d.arrow(points, label, at=at, start_marker="er-zero-one" if optional else "er-one", end_marker="er-many",
                head=False, sw=1.4, color=MUTED, dashed=optional, size=11)  # fmt: skip

    rel([(users.cx, users.b), (users.cx, tokens.y)])
    rel([(users.x, 200), (24, 200), (24, 620), (resets.x, 620)])
    rel([(users.r, 250), (320, 250), (320, 820), (events.r, 820)], optional=True)
    rel([(users.r, 160), (shows.x, 160)])
    rel([(shows.cx, shows.b), (shows.cx, uploads.y)])
    rel([(shows.r, 160), (items.x, 160)])
    rel([(items.r, 160), (chunks.x, 160)])
    rel([(shows.r, 300), (630, 300), (630, 420), (episodes.x, 420)])
    rel([(episodes.r, 420), (segments.x, 420)])
    rel([(episodes.r, 560), (940, 560), (940, 670), (claims.x, 670)])
    rel([(segments.cx, segments.b), (segments.cx, claims.y)], optional=True)
    rel([(episodes.cx, episodes.b), (episodes.cx, runs.y)])
    d.arrow(
        [(segments.r, 470), (1245, 470), (1245, 190), (chunks.r, 190)],
        head=True,
        dashed=True,
        color=FAINT,
        sw=1.2,
    )
    d.arrow(
        [(claims.r, 700), (1260, 700), (1260, 210), (chunks.r, 210)],
        head=True,
        dashed=True,
        color=FAINT,
        sw=1.2,
    )
    k = d.box(1290, 120, 270, 392, "Reading the diagram", None, [
        "PK primary key · FK foreign key", "UK unique (or unique per parent)", "",
        "Lines end with a crow's foot at", "the many side and two bars at", "the one side. A ring: the parent is",
        "optional (set null on delete).", "", "Grey dashed arrows: ids kept in", "arrays (citations), not foreign",
        "keys.", "", "Deleting a user deletes their", "tokens, resets and shows; their", "security events stay, unlinked.",
        "Deleting a show deletes its", "uploads, sections, chunks and", "episodes, down to claims and runs.",
    ], kind="note", line_size=12)  # fmt: skip
    del k
    d.text(
        1290, 548, "Migrations: db/init, then db/migrations/0003", size=12, color=MUTED, maxw=270
    )
    d.text(1290, 566, "to 0008, applied by db-migrate at start.", size=12, color=MUTED, maxw=270)
    return d


# ---- 11 --------------------------------------------------------------------------------------
def deployment() -> Diagram:
    d = new("11-deployment", 11, "Deployment: Docker Compose",
            "Every container, what it is built from, its ports, volumes and secrets, and the order they start in",
            h=1000)  # fmt: skip
    d.group(30, 110, 1540, 840, "Host: macOS · Docker Desktop (context desktop-linux)", fill=WHITE)
    d.group(50, 150, 1500, 640, "Docker network podcast-engine_default")

    def container(
        x, y, w, h, name, image, port=None, public=False, vols=(), extra=(), kind="service"
    ):
        b = d.box(x, y, w, h, name, image, extra, kind=kind, title_size=13.5, line_size=11.5)
        cy = y + h - 30
        cx = x + 12
        widths = [
            text_width(c, 10.5, mono=True) + 20 for c in ([port] if port else []) + list(vols)
        ]
        two_rows = port and vols and sum(widths) > w - 24
        if port:
            fill, stroke = KINDS["edge"] if public else KINDS["note"]
            py = cy - 26 if two_rows else cy
            pw = (
                d.chip(
                    cx,
                    py,
                    port,
                    fill=fill,
                    stroke=stroke if public else FAINT,
                    color=ACCENT if public else MUTED,
                )
                + 6
            )
            cx += 0 if two_rows else pw
        for v in vols:
            cx += d.chip(cx, cy, v, fill=KINDS["store"][0], stroke="#B7AED0", color="#5B4B8A") + 6
        if cx > x + w:
            d.problems.append(f"{d.slug}: chips overflow {name}")
        return b

    container(
        70,
        190,
        220,
        125,
        "web",
        "built from web/ · nginx 1.27",
        "8080 (open)",
        True,
        (),
        ["SPA + /api proxy"],
        kind="edge",
    )
    container(
        310,
        190,
        250,
        125,
        "api",
        "stage.Dockerfile target api",
        "127.0.0.1:8000",
        False,
        ("uploads",),
        ["uvicorn; 2 secrets"],
    )
    container(
        580,
        190,
        220,
        125,
        "scheduler",
        "stage image",
        None,
        False,
        ("scheduler_state",),
        ["refresh tick, 5 min"],
    )
    container(
        820,
        190,
        230,
        125,
        "vault",
        "hashicorp/vault:2.1.2",
        "127.0.0.1:8200",
        False,
        ("vaultdata", "vaulttls"),
        [],
        kind="security",
    )
    container(
        1070,
        190,
        200,
        125,
        "mailpit",
        "axllent/mailpit",
        "127.0.0.1:8025",
        False,
        (),
        ["SMTP inbox"],
        kind="support",
    )
    container(
        1290,
        190,
        240,
        125,
        "prometheus",
        "prom/prometheus:v3.14.0",
        "127.0.0.1:9090",
        False,
        ("prometheus_data",),
        [],
        kind="support",
    )
    d.group(
        70,
        335,
        1460,
        200,
        "Stage workers · stage.Dockerfile target worker, one image per stage (EXTRAS)",
    )
    workers = [("ingest", ["ingest_cache", "uploads (ro)"]), ("index", ["hf_cache"]), ("retrieve_plan", ["hf_cache", "prompts"]),
               ("script", ["prompts"]), ("factcheck", ["prompts"]), ("voice", ["tts_cache", "audio_scratch", "assets"]),
               ("assemble", ["audio_scratch", "assets"]), ("publish", ["feed_staging"])]  # fmt: skip
    for i, (name, vols) in enumerate(workers):
        x = 88 + i * 179
        d.box(
            x,
            372,
            168,
            145,
            name,
            "worker · :9100/metrics",
            (),
            kind="worker",
            title_size=13,
            pad=12,
        )
        for j, v in enumerate(vols):
            d.chip(
                x + 12, 432 + j * 26, v, fill=KINDS["store"][0], stroke="#B7AED0", color="#5B4B8A"
            )
    container(
        70,
        555,
        300,
        125,
        "postgres",
        "pgvector/pgvector:pg16",
        "5432 (dev only)",
        False,
        ("pgdata",),
        ["db/init on first start"],
        kind="store",
    )
    container(
        390,
        555,
        240,
        125,
        "redis",
        "redis:7-alpine",
        None,
        False,
        ("redisdata",),
        ["append-only file"],
        kind="store",
    )
    container(
        650,
        555,
        270,
        125,
        "s3",
        "rustfs/rustfs:1.0.1",
        "127.0.0.1:9001",
        False,
        ("s3data",),
        ["S3 API + console"],
        kind="store",
    )
    d.group(940, 555, 590, 210, "One-shot setup · runs at every up, then exits")
    chain = [("vault-certs", "CA + TLS cert"), ("vault-init", "unseal, token"), ("s3-init", "create bucket"),
             ("db-migrate", "apply migrations")]  # fmt: skip
    for i, (name, what) in enumerate(chain):
        x = 958 + i * 142
        d.box(x, 600, 130, 76, name, None, [what], kind="security" if "vault" in name else "plain", title_size=12.5,
              line_size=11, pad=11)  # fmt: skip
        if i:
            d.arrow([(x - 12, 638), (x, 638)], sw=1.3)
    d.text(
        958,
        700,
        "vault (healthy) runs between vault-certs and vault-init;",
        size=11.5,
        color=MUTED,
        maxw=560,
    )
    d.text(
        958,
        718,
        "s3-init and db-migrate wait for vault-init, then the api, the",
        size=11.5,
        color=MUTED,
        maxw=560,
    )
    d.text(
        958,
        736,
        "scheduler and the workers start; web waits for a healthy api.",
        size=11.5,
        color=MUTED,
        maxw=560,
    )
    kx = 70
    d.text(kx, 718, "Key", size=12, bold=True)
    kx += 40
    kx += (
        d.chip(kx, 705, "8080 (open)", fill=KINDS["edge"][0], stroke=KINDS["edge"][1], color=ACCENT)
        + 8
    )
    kx += d.text(kx, 719, "reachable from the network", size=11.5, color=MUTED) + 22
    kx += d.chip(kx, 705, "127.0.0.1:8000", stroke=FAINT, color=MUTED) + 8
    kx += d.text(kx, 719, "this computer only", size=11.5, color=MUTED) + 22
    kx += d.chip(kx, 705, "pgdata", fill=KINDS["store"][0], stroke="#B7AED0", color="#5B4B8A") + 8
    d.text(kx, 719, "named volume or mount", size=11.5, color=MUTED)
    d.rect(50, 808, 1500, 124, fill="#FAFAF9", stroke=RULE, rx=10)
    rows = [
        ("Secrets", "vault_app_token and vault_ca (Docker secrets) go to every application container; secrets/ is git-ignored"),
        ("Bind mounts", "./config, ./prompts and ./assets (read-only); ./db/migrations; ./web/nginx.conf; ./secrets (setup only)"),
        ("Health checks", "pg_isready · redis-cli ping · storage /health · vault status · api /health · workers: celery ping"),
        ("Images", "one Python 3.12 Dockerfile with targets api and worker; each stage installs only its extras"),
    ]  # fmt: skip
    for i, (head, text) in enumerate(rows):
        y = 834 + i * 25
        d.text(68, y, head, size=12, bold=True, maxw=130)
        d.text(200, y, text, size=12, maxw=1330)
    return d


# ---- 12 --------------------------------------------------------------------------------------
def web_app() -> Diagram:
    d = new("12-web-app", 12, "Web app",
            "The React single-page app, how it talks to the API, and how its typed client is generated", h=830)  # fmt: skip
    d.group(40, 125, 1010, 490, "Browser · React 19 single-page app (TypeScript 7, Vite 8)")
    d.box(58, 165, 480, 150, "Routes", "react-router 8", [
        "Public: /login, /setup, /forgot-password, /reset-password",
        "RequireAuth → AppShell: header, skip link, navigation",
        "/shows · /shows/new · /shows/:id (Episodes, Sources, PDF",
        "uploads, Settings) · /episodes/:id (Listen, Script, …)"], kind="client")  # fmt: skip
    d.box(556, 165, 476, 150, "Components and theme", "plain CSS with design tokens", [
        "White with dark orange #C2410C; AA contrast",
        "Button, fields, Tabs (arrow keys), ConfirmDialog",
        "(native <dialog>), ProgressSteps (announced),",
        "AudioPlayer, StatusBadge, Pagination, Alert"], kind="client")  # fmt: skip
    d.box(
        58,
        335,
        300,
        112,
        "AuthProvider",
        None,
        ["GET /v1/auth/me on load", "signIn, signOut (cookie)", "Any 401 → sign-in page"],
    )
    d.box(
        376,
        335,
        320,
        112,
        "TanStack Query",
        None,
        [
            "One hook per API call",
            "Changes refresh what they touch",
            "Lists poll while an episode runs",
        ],
    )
    events = d.box(
        714,
        335,
        318,
        112,
        "useEpisodeEvents",
        None,
        ["EventSource on …/events", "Writes each event into the cache", "Falls back to polling"],
    )
    client = d.box(58, 467, 974, 130, "Typed API client", "openapi-fetch", [
        "Types generated from the API's own OpenAPI description: src/api/schema.d.ts",
        "CSRF middleware: copies the pe_csrf cookie into X-CSRF-Token on every change",
        "Error middleware: { detail } → ApiError (status, Retry-After); 401 → sign-in",
        "Same origin + /api; credentials: same-origin; the session cookie is never readable"])  # fmt: skip
    nginx = d.box(1100, 165, 250, 432, "nginx", ":8080", [
        "/assets/*", "  cached for a year", "  (hashed file names)", "",
        "/ → index.html", "  CSP; no-cache", "",
        "/api/* → API", "  26 MB upload cap", "",
        "…/events (SSE)", "  unbuffered, 1 hour", "",
        "/api/metrics → 404", "Every page: nosniff,", "  same-origin referrer"], kind="edge")  # fmt: skip
    api = d.box(
        1400,
        300,
        160,
        200,
        "API",
        None,
        ["/v1 REST", "SSE events", "cookie + CSRF", "bearer, API keys"],
    )
    d.arrow([(client.r, client.cy), (nginx.x, client.cy)], "fetch")
    d.arrow([(events.r, events.cy), (nginx.x, events.cy)], "SSE")
    d.arrow([(nginx.r, api.cy), (api.x, api.cy)], "/v1/*")
    d.text(40, 665, "Build", size=14, bold=True)
    steps = ["FastAPI create_app().openapi()", "make openapi → web/openapi.json", "openapi-typescript → schema.d.ts",
             "tsc + vite build → web/dist", "Docker: node 22 → nginx 1.27"]  # fmt: skip
    x = 40
    for i, step in enumerate(steps):
        w = text_width(step, 12) + 28
        d.box(x, 681, w, 44, None, None, [step], kind="note", line_size=12, pad=14)
        if i:
            d.arrow([(x - 22, 703), (x, 703)], sw=1.3)
        x += w + 22
    d.text(40, 757, "make web-client runs the first three after an API change. Tests: Vitest with Testing Library "
           "(27 tests), plus a headless Playwright screenshot pass.", size=12, color=MUTED)  # fmt: skip
    return d


# ---- 13 --------------------------------------------------------------------------------------
def evaluation() -> Diagram:
    d = new("13-evaluation", 13, "Evaluation and research tooling",
            "How the three studies and the technical benchmarks are run, and where results land", h=920)  # fmt: skip

    def lane(y: float, name: str, steps: list[str], status: str, kind: str, h: float = 92) -> None:
        d.text(40, y + 28, name, size=15, bold=True)
        d.pill(40, y + 42, status, kind)
        x = 250
        for i, step in enumerate(steps):
            rows = step.split("\n")
            w = max(text_width(r, 12) for r in rows) + 30
            d.box(
                x,
                y,
                w,
                h,
                None,
                None,
                rows,
                kind="worker" if i < len(steps) else "plain",
                line_size=12,
                pad=15,
            )
            if i:
                d.arrow([(x - 26, y + h / 2), (x, y + h / 2)], sw=1.3)
            x += w + 26
        if x - 26 > 1560:
            d.problems.append(f"{d.slug}: lane {name} too wide ({x - 26:.0f}px)")

    lane(130, "Accuracy", ["topics.yaml\n30 topics", "generate.py: grounded and\nungrounded scripts, same\nmodel and settings",
                           "sheets.py: blinded,\nshuffled rating sheets,\nsource snapshots",
                           "Two raters\nRATING_GUIDE.md", "analyse.py: accuracy, 95% CI,\nunsupported rate, citation\ncoverage, kappa, paired test"],
         "ready: dry run passed", "success")  # fmt: skip
    lane(260, "Format", ["Two hosts vs one\nnarrator, same content", "Quiz, engagement,\ncompletion; about\n30 per group",
                         "stats.compare_independent:\nt-test or Mann-Whitney U,\nchosen by Shapiro-Wilk"],
         "open: needs participants", "note")  # fmt: skip
    lane(390, "Trust", ["Matched 3–5 min clips,\nAI-made and human-made,\nmusic removed; blind",
                        "Naturalness, trust,\nusefulness (1–5);\nrandom order", "stats.compare_paired,\nmean_interval; debrief\nafter the session"],
         "open: needs participants", "note")  # fmt: skip
    d.group(
        40,
        520,
        1000,
        260,
        "Technical benchmarks · run against a throwaway database (make bench-db, :55433)",
    )
    benches = [("run.py", ["Stage timing, loudness,", "silence, cost per episode"]), ("wer.py", ["Speech-to-text round", "trip (Whisper base.en)"]),
               ("gate.py", ["Fact-check catch rate", "on planted claims"]), ("stack.py", ["Parallel episodes and", "recovery on Docker"])]  # fmt: skip
    for i, (name, lines) in enumerate(benches):
        d.box(58 + i * 245, 560, 230, 100, name, None, lines, kind="worker", title_size=13)
    d.box(58, 680, 965, 82, "Latest measured (9 Oct 2026)", None, [
        "−16.00 LUFS, peak 0.96, no clipped samples · word error rate 4.3% · 31 s to make 3.7 min with say voices",
        "Fact-check proxy: 22 of 22 claims supported · cost USD 0 offline (the Gemini run is not yet measured)"], kind="note", line_size=12)  # fmt: skip
    d.box(1070, 520, 490, 260, "Results", None, [
        "evaluation/results/<kind>/<UTC time>/", "  results.json and report.md", "",
        "Page snapshots are cached on the first", "fetch, so every condition and rerun", "reads the same text.", "",
        "Audio, object stores and cached pages", "are git-ignored."], kind="note")  # fmt: skip
    d.text(48, 820, "Studies with people (format, trust, and possibly the raters) wait for research ethics board "
           "approval; the timeline plans approval by week 7.", size=12, color=MUTED)  # fmt: skip
    return d


# ---- 14 --------------------------------------------------------------------------------------
def observability() -> Diagram:
    d = new("14-observability", 14, "Observability",
            "Metrics, logs, run records and health checks: how to tell what the system is doing", h=780)  # fmt: skip
    d.group(40, 125, 860, 330, "Metrics · Prometheus")
    api = d.box(58, 170, 400, 120, "API", "/metrics (blocked at nginx)", [
        "podcast_http_requests_total", "  {method, route template, status}",
        "podcast_http_request_duration_seconds"])  # fmt: skip
    workers = d.box(58, 312, 400, 120, "Stage workers", ":9100/metrics on each", [
        "podcast_stage_runs_total {stage, outcome}", "podcast_stage_duration_seconds {stage}",
        "every attempt counts, retries included"], kind="worker")  # fmt: skip
    prom = d.box(560, 225, 320, 150, "Prometheus 3.14", "127.0.0.1:9090", [
        "Scrape jobs: prometheus, api,", "  stage_workers", "Stored in prometheus_data",
        "Config: monitoring/prometheus.yml"], kind="support")  # fmt: skip
    d.arrow(
        [(prom.x, 270), (510, 270), (510, api.cy), api.right()], "scrape", at=(535, 255), bg=False
    )
    d.arrow(
        [(prom.x, 335), (510, 335), (510, workers.cy), workers.right()],
        "scrape",
        at=(535, 352),
        bg=False,
    )
    d.group(930, 125, 630, 330, "Logs and records")
    d.box(948, 170, 594, 120, "Logs", "structlog: JSON lines to stdout", [
        "Every service: docker compose logs -f <service>",
        "Events such as page_ingested, email_sent, security_event",
        "Secrets, reset links and email bodies are never logged"], kind="support")  # fmt: skip
    d.box(948, 312, 594, 120, "Records in PostgreSQL", None, [
        "stage_runs: seconds, model, prompt version and seed per attempt",
        "episodes: status, stage, error, rewrite count (live in the web app)",
        "security_events: sign-ins, failures, locks, resets, keys, accounts"], kind="store")  # fmt: skip
    d.box(40, 485, 1520, 112, "Health", None, [
        "/health: the API process answers (liveness) · /ready: database, queue and storage all answer, else 503 naming the one that failed",
        "Compose health checks gate the start-up order: pg_isready, redis-cli ping, storage /health, vault status, api /health, a celery ping per worker",
        "The web app's episode page follows progress live (server-sent events) and shows the stage and any error in words",
    ], kind="success", line_size=12.5)  # fmt: skip
    d.legend(48, 640, ["service", "worker", "support", "store", ("success", "Health checks")])
    return d


MORE = [api_layers, security, sign_in_sequence, generation_sequence, data_model, deployment, web_app, evaluation,
        observability]  # fmt: skip
