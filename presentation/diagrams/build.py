#!/usr/bin/env python3
"""Architecture diagrams of AI Podcast Engine.

    python presentation/diagrams/build.py        # writes presentation/diagrams/svg/*.svg

Each diagram is drawn from the code as it is (October 2026). Change a diagram here, not in the
SVG. Then export PNGs and the PDF with render.mjs (see README.md).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from svgkit import ACCENT, INK, MUTED, RULE, Box, Diagram, text_width

OUT = Path(__file__).resolve().parent / "svg"
TOTAL = 14


def new(slug: str, number: int, title: str, subtitle: str, **size: int) -> Diagram:
    return Diagram(slug, number, TOTAL, title, subtitle, **size)


def footnote(d: Diagram, y: float, rows: list[str]) -> None:
    for i, row in enumerate(rows):
        d.text(48, y + i * 18, row, size=12, color=MUTED, maxw=d.w - 96)


# ---- 01 --------------------------------------------------------------------------------------
def system_context() -> Diagram:
    d = new("01-system-context", 1, "System context",
            "Who uses AI Podcast Engine, and the outside systems it relies on")  # fmt: skip
    system = d.box(620, 170, 360, 560, None, None, (), kind="system")
    d.text(system.cx, 238, "AI Podcast Engine", size=22, bold=True, anchor="middle")
    d.text(system.cx, 262, "This project", size=12, color=MUTED, anchor="middle")
    about = ["Turns live sources into grounded,", "two-host podcast episodes: it fetches",
             "and indexes the sources, writes a script", "that cites them, fact-checks every",
             "claim, voices, assembles and publishes,", "and refreshes an episode when its",
             "sources change."]  # fmt: skip
    for i, row in enumerate(about):
        d.text(system.cx, 304 + i * 21, row, size=13, anchor="middle", maxw=330)
    d.line(660, 474, 940, 474, color="#F1C7AA")
    d.text(
        system.cx, 502, "INSIDE", size=10.5, bold=True, color=ACCENT, anchor="middle", spacing=1.2
    )
    rows = [["Web app (nginx)", "API"], ["Scheduler", "8 stage workers"], ["PostgreSQL + pgvector", "Redis"],
            ["Object storage", "Vault", "Mailpit"], ["Prometheus"]]  # fmt: skip
    for r, names in enumerate(rows):
        widths = [text_width(n, 11.5) + 14 for n in names]
        x = system.cx - (sum(widths) + 8 * (len(names) - 1)) / 2
        for n, w in zip(names, widths, strict=True):
            d.chip(x, 518 + r * 32, n, mono=False, size=11.5, h=22, stroke="#F1C7AA")
            x += w + 8
    people = [
        ("Creator", ["Creates shows, reviews and", "approves scripts, listens"], 190, "Creates shows, reviews,\napproves (web app)"),
        ("Administrator", ["Manages accounts and reads", "the security log"], 390, "Manages accounts\n(web app, API)"),
        ("Listener", ["Subscribes in a podcast app;", "plays audio, reads notes"], 590, "RSS feed, audio, notes\n(public)"),
    ]  # fmt: skip
    for name, lines, y, label in people:
        b = d.box(80, y, 300, 120, name, None, lines, kind="person", icon="person")
        d.arrow([b.right(), (system.x, b.cy)], label, at=(500, b.cy))
    externals = [
        ("Source websites", "Pages, RSS and Atom feeds", ["Read and re-read for changes;", "creators also upload PDFs"], 170, "Fetches, re-checks"),
        ("Language model", "Gemini 3.8 Flash, or Claude", ["Outlines, scripts and judges", "claims (offline fallbacks)"], 320, "Prompts, structured\nanswers"),
        ("Speech synthesis", "Chatterbox (local) or Gemini TTS", ["One voice per host; a cloned", "voice needs written consent"], 470, "Lines to speak"),
        ("Email (SMTP)", "Mailpit inbox locally", ["Password-reset links", "and account notices"], 620, "Reset links, notices"),
    ]  # fmt: skip
    for name, tech, lines, y, label in externals:
        b = d.box(1220, y, 320, 110, name, tech, lines, kind="external")
        d.arrow([(system.r, b.cy), b.left()], label, at=(1100, b.cy))
    d.legend(48, 790, ["person", "system", "external"])
    footnote(d, 822, ["Everything runs on one Docker Compose stack. Only the web app (port 8080) is reachable "
                      "from the network; the rest is bound to this computer or internal."])  # fmt: skip
    return d


# ---- 02 --------------------------------------------------------------------------------------
STAGES = [
    ("Ingest", ["Pages, feeds, PDFs", "SHA-256 per section"]),
    ("Index", ["Chunk and embed", "bge-small, pgvector"]),
    ("Retrieve, plan", ["Rank passages", "Outline segments"]),
    ("Script", ["Two-host dialogue", "Every claim cited"]),
    ("Fact-check", ["Judge each claim", "Rewrite or hold"]),
    ("Voice", ["Speech per line", "Cached by content"]),
    ("Assemble", ["Join, −16 LUFS", "Silence, clipping"]),
    ("Publish", ["Notes and RSS feed", "Rebuilt per show"]),
]


def containers() -> Diagram:
    d = new("02-containers", 2, "Containers",
            "The running pieces, what each one does, and how requests and jobs flow between them",
            h=1000)  # fmt: skip
    browser = d.box(
        40, 150, 200, 120, "Browser", "React 19 SPA", ["Creators and admins"], kind="client"
    )
    apps = d.box(
        40,
        320,
        200,
        110,
        "Podcast apps",
        None,
        ["Listeners: RSS feed,", "audio and show notes"],
        kind="client",
    )
    web = d.box(330, 150, 210, 280, "Web", "nginx 1.27 · :8080", [
        "Serves the built SPA", "Proxies /api to the API", "Streams SSE unbuffered",
        "CSP, security headers", "Long cache for assets"], kind="edge")  # fmt: skip
    api = d.box(600, 150, 260, 180, "API", "FastAPI · Python 3.12 · :8000", [
        "REST under /v1, plus SSE", "Sign-in: cookie + CSRF, bearer,", "API keys; owner-scoped data",
        "Serves audio, notes and PDFs", "/metrics for Prometheus"])  # fmt: skip
    redis = d.cylinder(
        600,
        372,
        260,
        108,
        "Redis 7",
        None,
        ["Celery broker: a queue per stage", "Login-attempt counters"],
    )
    sched = d.box(
        600,
        520,
        260,
        95,
        "Scheduler",
        None,
        ["Every 5 min: starts a refresh", "for each show that is due"],
    )
    group = d.group(920, 130, 370, 490, "Stage workers · one container each")
    boxes: list[Box] = []
    for i, (name, lines) in enumerate(STAGES):
        col, row = divmod(i, 4)
        boxes.append(d.box(935 + col * 180, 165 + row * 110, 160, 92, name, None, lines, kind="worker",
                           badge=str(i + 1), title_size=13, line_size=11.5))  # fmt: skip
    for i in (0, 1, 2, 4, 5, 6):
        a, b = boxes[i], boxes[i + 1]
        d.arrow([a.bottom(), b.top()], head=True, color="#2E6B5E", sw=1.2)
    d.arrow(
        [boxes[3].right(0.5), (1105, boxes[3].cy), (1105, boxes[4].cy), boxes[4].left(0.5)],
        color="#2E6B5E",
        sw=1.2,
    )
    ext = [("Source websites", None, ["Pages, RSS/Atom feeds"], 150),
           ("Language model", "Gemini 3.8 Flash or Claude", ["Outline, script, judging"], 290),
           ("Speech synthesis", "Chatterbox or Gemini TTS", ["One voice per host"], 430)]  # fmt: skip
    for name, tech, lines, y in ext:
        b = d.box(1340, y, 220, 110, name, tech, lines, kind="external")
        d.arrow([(group.r, b.cy), b.left()])
    d.box(
        1340,
        570,
        220,
        50,
        None,
        None,
        ["Model and speech calls come", "from stages 3–6"],
        kind="note",
        line_size=11,
        pad=10,
    )
    d.box(
        320,
        690,
        220,
        120,
        "Prometheus",
        "3.14 · :9090",
        ["Scrapes the API and", "every worker"],
        kind="support",
    )
    pg = d.cylinder(600, 690, 260, 120, "PostgreSQL 16 + pgvector", None, [
        "Shows, episodes, claims, runs", "Sections; chunks: vector(384)", "Users, tokens, security log"])  # fmt: skip
    s3 = d.cylinder(
        920,
        690,
        270,
        120,
        "Object storage",
        "RustFS · S3 API",
        ["Line audio, episode WAV", "Show notes, RSS feeds, PDFs"],
    )
    d.box(
        1210,
        690,
        170,
        120,
        "Vault 2.1",
        "HTTPS · own CA",
        ["Model keys, token", "key, SMTP password"],
        kind="security",
    )
    d.box(
        1400,
        690,
        160,
        120,
        "Mailpit",
        "SMTP · :8025",
        ["Local inbox for", "reset emails"],
        kind="support",
    )
    d.arrow([browser.right(0.5), (web.x, browser.cy)], "HTTPS")
    d.arrow([apps.right(0.5), (web.x, apps.cy)], "feed, audio")
    d.arrow([(web.r, 240), (api.x, 240)], "/api/*")
    d.arrow([(700, api.b), (700, redis.y)], "enqueue", at=(652, 351))
    d.arrow([(760, sched.y), (760, redis.b)], "refresh", at=(808, 500))
    d.arrow([(redis.r, 426), (group.x, 426)], "jobs")
    d.arrow([(api.x, 300), (575, 300), (575, 750), (pg.x, 750)], "SQL", at=(575, 640))
    d.arrow([(730, sched.b), (730, pg.y)], "shows due", at=(790, 652))
    d.arrow([(group.x, 575), (885, 575), (885, 735), (pg.r, 735)], "state", at=(885, 655))
    d.arrow([(1055, group.b), (1055, s3.y)], "audio, notes, feeds", at=(1055, 655))
    d.legend(
        48, 880, ["client", "edge", "service", "worker", "store", "security", "support", "external"]
    )
    footnote(d, 908, ["Not drawn, to keep it readable: every service reads its secrets from Vault at start "
                      "(HTTPS, read-only token); the API streams media from object storage and sends mail",
                      "through SMTP; Prometheus scrapes the API and every worker. One-shot setup containers "
                      "are in the deployment diagram."])  # fmt: skip
    return d


# ---- 03 --------------------------------------------------------------------------------------
PIPELINE = [
    (
        "Ingest",
        ["Fetch pages, feeds", "and uploaded PDFs", "Split into sections"],
        ["source_items", "+ content hash"],
    ),
    ("Index", ["Chunk new or", "changed sections", "Embed: bge-small"], ["chunks", "vector(384)"]),
    (
        "Retrieve, plan",
        ["Rank: relevance,", "recency, reliability", "Outline segments"],
        ["segments", "+ source ids"],
    ),
    (
        "Script",
        ["Two-host dialogue", "Each claim cites", "its passages"],
        ["episodes.script", "lines + claims"],
    ),
    (
        "Fact-check",
        ["Judge each claim", "against its cited", "passages"],
        ["claims + verdicts", "fact_check"],
    ),
    (
        "Voice",
        ["One voice per host", "Reuse lines voiced", "before (by content)"],
        ["line audio (S3)", "voice manifest"],
    ),
    (
        "Assemble",
        ["Intro, transitions,", "outro; −16 LUFS;", "silence, clipping"],
        ["episode WAV (S3)", "chapters"],
    ),
    (
        "Publish",
        ["Show notes with", "citations; rebuild", "the RSS feed"],
        ["notes.md (S3)", "feeds/<show>.xml"],
    ),
]


def pipeline() -> Diagram:
    d = new("03-pipeline", 3, "The episode pipeline",
            "Eight stages, one worker each, chained through Redis queues; the fact-check gate can send work back")  # fmt: skip
    w, gap, y, h = 176, 16, 230, 250
    boxes = []
    for i, (name, does, writes) in enumerate(PIPELINE):
        x = 40 + i * (w + gap)
        b = d.box(
            x,
            y,
            w,
            h,
            name,
            None,
            does,
            kind="worker",
            badge=str(i + 1),
            title_size=13,
            line_size=12,
        )
        d.line(x + 12, y + 150, x + w - 12, y + 150, color="#B9D3C9")
        d.text(x + 14, y + 172, "WRITES", size=10, bold=True, color="#2E6B5E", spacing=1)
        for j, value in enumerate(writes):
            d.text(x + 14, y + 192 + j * 17, value, size=11.5, mono=True, color=INK, maxw=w - 28)
        boxes.append(b)
        if i:
            prev = boxes[i - 1]
            d.arrow([(prev.r, y + 70), (x, y + 70)], color="#2E6B5E", sw=1.4)
    d.text(
        40,
        205,
        "Each stage hands the episode to the next through that stage's Redis queue",
        size=12,
        color=MUTED,
    )
    script, check, voice = boxes[3], boxes[4], boxes[5]
    d.arrow(
        [check.top(0.5), (check.cx, 175), (script.cx, 175), script.top(0.5)], color=ACCENT, sw=1.6
    )
    d.label(
        (script.cx + check.cx) / 2,
        158,
        "unsupported claims: rewrite (at most twice)",
        color=ACCENT,
        bg=False,
    )
    unchanged = d.box(
        40,
        560,
        270,
        90,
        "Stops: unchanged",
        None,
        ["No section changed since the", "last episode: nothing to say"],
        kind="note",
    )
    d.arrow([boxes[0].bottom(0.5), (boxes[0].cx, unchanged.y)], "no change", at=(boxes[0].cx, 520))
    review = d.box(800, 560, 380, 110, "Held for review · needs_review", None, [
        "Still unsupported after two rewrites, or the", "show reviews every script before voicing.",
        "A person edits lines or approves it."], kind="edge")  # fmt: skip
    d.arrow([(860, check.b), (860, review.y)], "hold", at=(860, 520))
    d.arrow([(930, review.y), (930, check.b)], "edit: re-check", at=(965, 520), anchor="start")
    d.arrow([(1110, review.y), (1110, voice.b)], "approve", at=(1110, 520))
    d.box(1230, 560, 330, 110, "Any stage error → failed", None, [
        "The episode keeps the stage it reached;", "retry resumes there. Cancel stops after",
        "the stage that is running."], kind="danger")  # fmt: skip
    infos = [
        ("Queues", ["One Redis queue per stage; a worker reads only its own.",
                    "Jobs are acknowledged late: a crashed job is redelivered."]),
        ("Run records", ["Every attempt writes a stage_runs row: seconds, model,",
                         "prompt version and seed, so a run can be repeated."]),
        ("Models", ["Language model in stages 3–5 (offline fallbacks without",
                    "a key); embeddings in 2; speech synthesis in 6."]),
    ]  # fmt: skip
    for i, (title, lines) in enumerate(infos):
        d.box(40 + i * 512, 712, 496, 92, title, None, lines, kind="note", line_size=12)
    d.legend(48, 838, [("worker", "Pipeline stage"), ("edge", "Waits for a person"), ("danger", "Error path"),
                       ("note", "Outcome or note")], extra=[("solid", "hands on to")])  # fmt: skip
    return d


# ---- 04 --------------------------------------------------------------------------------------
def lifecycle() -> Diagram:
    d = new("04-episode-lifecycle", 4, "Episode lifecycle",
            "Every status an episode can have, and what moves it from one to the next", h=820)  # fmt: skip

    def state(x: float, y: float, w: float, name: str, sub: str, kind: str) -> Box:
        return d.box(
            x,
            y,
            w,
            80,
            name,
            None,
            [sub],
            kind=kind,
            align="center",
            rx=22,
            title_size=15,
            line_size=11.5,
        )

    d.add(f'<circle cx="95" cy="400" r="9" fill="{INK}"/>')
    queued = state(150, 360, 190, "queued", "waiting for a worker", "plain")
    proc = state(420, 340, 240, "processing", "stage: ingest … publish", "service")
    published = state(1180, 360, 220, "published", "audio, notes, in the feed", "success")
    unchanged = state(1180, 190, 220, "unchanged", "no source changed", "note")
    failed = state(800, 110, 220, "failed", "error names the stage", "danger")
    review = state(800, 560, 220, "needs_review", "waiting for a person", "edge")
    cancelled = state(420, 620, 240, "cancelled", "nothing more runs", "note")
    d.arrow([(104, 400), queued.left()], "start or\nrefresh", at=(125, 440), bg=False)
    d.arrow([queued.right(), (proc.x, 400)], "worker picks\nup ingest", at=(380, 445), bg=False)
    d.arrow(
        [(450, proc.y), (450, 300), (520, 300), (520, proc.y)],
        "next stage",
        at=(485, 286),
        bg=False,
    )
    d.arrow([(proc.r, 400), published.left()], "publish stage done", at=(930, 388))
    d.arrow(
        [(640, proc.y), (640, 230), unchanged.left()], "ingest: nothing changed", at=(1000, 218)
    )
    d.arrow([(580, proc.y), (580, 150), (failed.x, 150)], "a stage fails", at=(690, 138))
    d.arrow(
        [(failed.x, 175), (610, 175), (610, proc.y)],
        "retry: resume\nat that stage",
        at=(705, 190),
        bg=False,
    )
    d.arrow(
        [(560, proc.b), (560, 600), (review.x, 600)],
        "fact-check holds it, or\nthe show reviews first",
        at=(690, 572),
        bg=False,
    )
    d.arrow(
        [(850, review.y), (850, 480), (640, 480), (640, proc.b)],
        "approve → voice\nedit → re-check",
        at=(745, 505),
        bg=False,
    )
    d.arrow([(460, proc.b), (460, cancelled.y)], "cancel", at=(432, 540), bg=False)
    d.arrow([(245, queued.b), (245, 660), cancelled.left()], "cancel", at=(245, 560))
    d.arrow([(910, review.b), (910, 680), (cancelled.r, 680)], "cancel", at=(800, 668))
    d.arrow([(520, cancelled.y), (520, proc.b)], "retry", at=(535, 540), anchor="start", bg=False)
    d.box(1180, 560, 360, 120, "Deleting", None, [
        "Allowed in any status except queued and", "processing: cancel first. It removes the",
        "audio and notes, and rewrites the feed if", "the episode was published."], kind="note", line_size=11.5)  # fmt: skip
    return d


# ---- 05 --------------------------------------------------------------------------------------
def refresh() -> Diagram:
    d = new("05-refresh", 5, "Keeping episodes current",
            "A refresh regenerates only what its changed sources touch, and reuses the rest", h=840)  # fmt: skip
    row1 = 150
    sched = d.box(
        40,
        row1,
        220,
        120,
        "Scheduler",
        "every 5 minutes",
        ["Finds shows due for a", "refresh (interval setting)"],
    )
    ep = d.box(
        300,
        row1,
        220,
        120,
        "New episode",
        "revision + 1, queued",
        ["Starts at ingest, like", "any episode"],
    )
    ingest = d.box(
        560,
        row1,
        240,
        120,
        "Ingest",
        None,
        ["Fetch every source again;", "SHA-256 of each section,", "compared with the stored one"],
        kind="worker",
        badge="1",
    )
    dx, dy, dw, dh = 850, row1 + 0, 180, 120
    d.add(f'<path d="M{dx + dw / 2},{dy} L{dx + dw},{dy + dh / 2} L{dx + dw / 2},{dy + dh} L{dx},{dy + dh / 2} Z" '
          f'fill="#FFF4EC" stroke="{ACCENT}" stroke-width="1.4" filter="url(#shadow)"/>')  # fmt: skip
    d.text(dx + dw / 2, dy + dh / 2 - 2, "Any section", size=13, bold=True, anchor="middle")
    d.text(dx + dw / 2, dy + dh / 2 + 15, "changed?", size=13, bold=True, anchor="middle")
    index = d.box(
        1090,
        row1,
        240,
        120,
        "Index",
        None,
        ["Re-embed only new or", "changed sections; others", "keep their chunks"],
        kind="worker",
        badge="2",
    )
    stop = d.box(850, 316, 180, 76, "Stop: unchanged", None, ["Nothing new to say"], kind="note")
    d.arrow([sched.right(), ep.left()])
    d.arrow([ep.right(), ingest.left()])
    d.arrow([ingest.right(), (dx, dy + dh / 2)])
    d.arrow([(dx + dw, dy + dh / 2), index.left()], "yes", at=(1060, dy + dh / 2 - 12))
    d.arrow(
        [(dx + dw / 2, dy + dh), (dx + dw / 2, stop.y)],
        "no",
        at=(958, dy + dh + 23),
        anchor="start",
        bg=False,
    )
    w, gap, y2 = 240, 12, 460
    steps = [
        ("Retrieve, plan", "3", ["Rank again; a segment", "whose sources changed is", "marked needs_script"], False),
        ("Script", "4", ["Rewrite marked segments;", "reuse the lines of the", "others unchanged"], False),
        ("Fact-check", "5", ["Check the claims of", "rewritten segments;", "rewrite or hold"], False),
        ("Voice", "6", ["Reuse cached line audio", "by content; new lines get", "the same voice and seed"], False),
        ("Assemble", "7", ["Join the lines; normalise", "again to −16 LUFS;", "crossfade the joins"], True),
        ("Publish", "8", ["New show notes; feed", "rebuilt with the new", "revision"], False),
    ]  # fmt: skip
    boxes = []
    for i, (name, n, lines, planned) in enumerate(steps):
        b = d.box(40 + i * (w + gap), y2, w, 130, name, None, lines, kind="worker", badge=n)
        if planned:
            d.pill(40 + i * (w + gap) + w - 84, y2 + 10, "planned", "edge")
        if boxes:
            d.arrow([(boxes[-1].r, y2 + 65), (b.x, y2 + 65)], color="#2E6B5E", sw=1.4)
        boxes.append(b)
    d.arrow(
        [index.bottom(0.5), (index.cx, 425), (boxes[0].cx, 425), boxes[0].top(0.5)],
        color="#2E6B5E",
        sw=1.4,
    )
    d.pill(40 + (w + gap) + w - 84, y2 + 10, "+ planned", "edge")
    rows = [
        ("Reused as is", "unchanged sections and their chunks and vectors · the lines of unaffected segments · line audio already voiced"),
        ("Regenerated", "changed sections · their chunks · segments that cite them · those claims and verdicts · the episode WAV, notes and feed"),
        ("Planned", "the rewrite sees the neighbouring lines as fixed context, and joins are crossfaded, so a refreshed segment does not sound spliced in"),
    ]  # fmt: skip
    for i, (head, text) in enumerate(rows):
        yy = 640 + i * 44
        d.rect(
            40,
            yy,
            1520,
            36,
            fill="#FAFAF9" if i != 2 else "#FFF4EC",
            stroke=RULE if i != 2 else ACCENT,
            rx=8,
        )
        d.text(56, yy + 23, head, size=12.5, bold=True, maxw=140)
        d.text(200, yy + 23, text, size=12.5, color=INK, maxw=1340)
    return d


if __name__ == "__main__":
    from diagrams_more import MORE

    OUT.mkdir(parents=True, exist_ok=True)
    built = [f() for f in (system_context, containers, pipeline, lifecycle, refresh, *MORE)]
    problems = [p for d in built for p in d.problems]
    if problems:
        raise SystemExit("Text does not fit:\n  " + "\n  ".join(problems))
    for d in built:
        print("wrote", d.save(OUT).name)
