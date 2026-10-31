"""Render the defect and risk report (PE-DRR-001) as a PDF.

    pip install -e ".[reports]"
    python docs/reports/defect_risk_report.py

The register below is the source of truth: when an item changes, edit its entry (status, dates,
notes), bump VERSION, add a REVISIONS line, and render again. Structure and fields follow the
public sources listed in REFERENCES; see section 3 of the report.
"""

from dataclasses import dataclass, field
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

DOC_ID = "PE-DRR-001"
TITLE = "Defect and Risk Report"
SYSTEM = "AI Podcast Engine"
VERSION = "1.1"
ISSUED = "31 October 2026"
OUT = Path(__file__).with_name(f"{DOC_ID}_defect-and-risk-report.pdf")

REVISIONS = [
    ("1.0", "31 Oct 2026", "First issue: 13 items from the review of 31 October 2026."),
    (
        "1.1",
        "31 Oct 2026",
        "PE-001 fixed, awaiting confirmation testing. PE-006: copies located, rotation "
        "command added; revocation awaits the owner.",
    ),
]

# ---- rating scales (project-defined; see section 4) ------------------------------------------
LIKELIHOOD = ["Rare", "Unlikely", "Possible", "Likely", "Almost certain"]
IMPACT = ["Negligible", "Minor", "Moderate", "Major", "Severe"]


def band(level: int) -> str:
    if level >= 20:
        return "Very high"
    if level >= 10:
        return "High"
    if level >= 5:
        return "Medium"
    return "Low"


@dataclass
class Item:
    id: str
    title: str
    kind: str  # Defect | Product risk | Project risk
    quality: str  # ISO/IEC 25010:2023 characteristic, or "n/a (project)"
    observed: str
    severity: str
    priority: str
    likelihood: int
    impact: int
    status: str
    object: str
    context: str
    description: list[str]
    expected: str
    actual: str
    response: str  # mitigation | acceptance | transfer | contingency
    recommendation: list[str]
    acceptance: list[str]
    references: list[str] = field(default_factory=list)
    progress: list[str] = field(default_factory=list)  # what has been done, newest last

    @property
    def level(self) -> int:
        return self.likelihood * self.impact


ENV = (
    "Local Docker Compose stack (14 services) on macOS, Apple M1; branch include_ml_model at "
    "commit 3331815 plus uncommitted changes; web app at http://localhost:8080."
)

ITEMS = [
    Item(
        id="PE-001",
        title="The Docker voice worker takes voicing jobs it cannot run",
        kind="Defect",
        quality="Reliability",
        observed="31 Oct 2026",
        severity="High",
        priority="P1",
        likelihood=5,
        impact=4,
        status="Awaiting confirmation testing",
        object="Voice stage: the voice service in docker-compose.yml and make voice-host.",
        context=(
            "Episode generation after a plain docker compose up -d, with TTS_BACKEND=chatterbox."
        ),
        description=[
            "Chatterbox (voice cloning) runs only on the Mac's GPU, in the host worker started by "
            "make voice-host. The Docker voice image does not include it.",
            "Reproduction: 1) docker compose up -d. 2) docker compose exec voice printenv "
            'TTS_BACKEND prints chatterbox. 3) docker compose exec voice python -c "import '
            "chatterbox\" fails with ModuleNotFoundError: No module named 'chatterbox'. 4) Any "
            "episode that reaches the voice step on this worker fails.",
            "make voice-host stops the Docker worker, but the next docker compose up -d starts it "
            "again. With both running, whichever worker takes a job decides whether it succeeds.",
        ],
        expected="Only a worker able to run the configured voice backend takes voicing jobs.",
        actual="The Docker worker accepts Chatterbox jobs and fails them.",
        response="Mitigation",
        recommendation=[
            "Put the Docker voice service in a Compose profile (for example docker-voice), so it "
            "starts only when that profile is active. Services without a profile always start; "
            "profiled ones start only with --profile or COMPOSE_PROFILES [11].",
            "Make the voice worker refuse to start when its configured backend cannot be loaded, "
            "with a log line naming the missing package, so a misconfiguration fails at once.",
        ],
        acceptance=[
            "With TTS_BACKEND=chatterbox, the Docker voice worker takes no job and stays stopped "
            "after docker compose up -d. (Done 31 Oct 2026.)",
            "A unit test shows the worker stands down when its backend cannot be imported. "
            "(Done 31 Oct 2026.)",
            "With make voice-host running, an episode is voiced and published end to end. "
            "(Pending: needs one episode run.)",
        ],
        references=["[11]"],
        progress=[
            "31 Oct 2026: the voice worker now checks, before taking any job, that its backend "
            "can be loaded (backend_unavailable in stages/voice/backends.py). Without it, it "
            "logs voice_worker_standing_down with the reason and exits 0; the voice service's "
            "restart policy is on-failure, so it stays stopped. Voicing jobs wait in the queue "
            "for the host worker instead of failing.",
            "Chosen over a Compose profile: it needs no configuration and covers every backend.",
            "Verified: the rebuilt container exited 0 with the reason logged; restart policy "
            "on-failure; make voice-host reached ready; 4 new unit tests, 303 passing.",
            "Also fixed: a plain docker compose up -d no longer cuts the host worker off. "
            "COMPOSE_FILE in .env now includes docker-compose.voice-host.yml, so the database, "
            "queue and storage ports stay published.",
        ],
    ),
    Item(
        id="PE-002",
        title="The shared Gemini free-tier quota limits output and can be used up by any account",
        kind="Product risk",
        quality="Performance efficiency",
        observed="25 Oct 2026",
        severity="High",
        priority="P2",
        likelihood=4,
        impact=4,
        status="Open",
        object="Gemini text and speech requests: common/quota.py, the pipeline and the assistant.",
        context="Episode generation and assistant questions on the free tier.",
        description=[
            "Gemini rate limits apply per project, not per API key, and requests-per-day quotas "
            "reset at midnight Pacific time [7]. Every account on this server, and the assistant, "
            "share one project's quota.",
            "The caps set here are LLM_REQUESTS_PER_DAY=18 and TTS_REQUESTS_PER_DAY=12, chosen "
            "below the limits shown for this project in AI Studio. An episode needs about four "
            "text requests, plus one per rewrite.",
            "Evidence: four of the eight failed episodes stopped on quota (9ce7125e and f8a1f1e7 "
            "on Gemini's own limit, f70004c8 and 6d0a7033 on this server's budget guard). Sign-up "
            "is open and Google sign-in is now available, so a new account can spend the day's "
            "budget for everyone.",
        ],
        expected="Each account can generate its episodes without exhausting the others' quota.",
        actual="Throughput is about four episodes a day in total, shared by all accounts.",
        response="Mitigation, with a contingency",
        recommendation=[
            "Enable billing for the project: to move from the Free tier to a paid tier, billing "
            "must first be set up in AI Studio [7].",
            "Otherwise, set SIGNUP_OPEN=false, or add a per-account daily episode limit.",
            "Contingency: LLM_ENABLED=false writes offline (extractive) scripts with no Gemini "
            "requests.",
        ],
        acceptance=[
            "Either billing is enabled and the caps are raised, or a test shows a second account "
            "is refused once its own daily limit is reached while others can still generate.",
            "The sidebar budget card shows the remaining requests correctly.",
        ],
        references=["[7]"],
    ),
    Item(
        id="PE-003",
        title="An admitted episode can still run out of budget partway through",
        kind="Defect",
        quality="Reliability",
        observed="28 Oct 2026",
        severity="Medium",
        priority="P2",
        likelihood=3,
        impact=3,
        status="Open",
        object="Budget check at the plan stage (stages/retrieve_plan/service.py).",
        context="Episode 6d0a7033, generated while other requests were spending the same budget.",
        description=[
            "The plan stage checks that a whole episode fits in today's budget before starting, "
            "but does not reserve those requests. Requests made in between (the assistant, other "
            "episodes) can spend them.",
            "Evidence: 6d0a7033 passed planning, then failed at the script step with "
            "\"Today's Gemini budget cannot cover another gemini-3.8-flash request ... (0 of "
            "today's 18 left)\".",
        ],
        expected="An episode admitted by the budget check can finish.",
        actual="It can fail at a later step when the budget runs out.",
        response="Mitigation",
        recommendation=[
            "Reserve the episode's estimated requests in Redis when it is admitted, draw them "
            "down as it runs, and release what is left when it ends or fails.",
        ],
        acceptance=[
            "A test with concurrent assistant requests cannot starve an admitted episode.",
            "Reserved requests are released when an episode fails or is cancelled.",
        ],
    ),
    Item(
        id="PE-004",
        title="The natural-dialogue script and delivery styles have not been tried in a live run",
        kind="Product risk",
        quality="Functional suitability",
        observed="31 Oct 2026",
        severity="Medium",
        priority="P2",
        likelihood=3,
        impact=3,
        status="Open",
        object="prompts/script.v3.md, the delivery tags and ChatterboxBackend.STYLES.",
        context="The goal: Gemini writes the script and the recorded voices read it naturally.",
        description=[
            "Prompt v3 (reactions, follow-up questions, one delivery tag per line) and the "
            "Chatterbox settings for each tag are covered only by tests with fakes.",
            "The one episode voiced with the cloned voice (e03ee93c) was written before v3, so "
            "every line was read as neutral.",
        ],
        expected="A live episode shows varied, tagged delivery that sounds conversational.",
        actual="Not yet observed.",
        response="Mitigation",
        recommendation=[
            'Generate one episode on the show "new sample test" with make voice-host running '
            "(about four text requests), listen, then tune the styles.",
        ],
        acceptance=[
            "The episode publishes, its Script tab shows delivery tags, and the owner approves "
            "how it sounds.",
        ],
    ),
    Item(
        id="PE-005",
        title="Google sign-in is refused: redirect_uri_mismatch",
        kind="Defect",
        quality="Functional suitability",
        observed="31 Oct 2026",
        severity="Medium",
        priority="P1",
        likelihood=5,
        impact=2,
        status="Open",
        object="Sign in with Google (api/google_sign_in.py) and the OAuth client in Google Cloud.",
        context="First sign-in attempt after configuring the client ID and secret.",
        description=[
            "GET /api/v1/auth/google/start redirects to Google correctly, with redirect_uri "
            "http://localhost:8080/api/v1/auth/google/callback. Google answers with its "
            "redirect_uri_mismatch error page.",
            "Google requires the redirect_uri to exactly match one of the client's authorized "
            "redirect URIs; redirect_uri_mismatch means it does not [8].",
            "Password sign-in is unaffected.",
        ],
        expected="Google shows the account chooser and returns to the app.",
        actual="Google refuses the request before showing the account chooser.",
        response="Mitigation",
        recommendation=[
            "Add http://localhost:8080/api/v1/auth/google/callback, exactly, to the OAuth "
            "client's Authorized redirect URIs [8].",
            "Test users are not needed: the app requests only openid and email, and apps that "
            "request a subset of name, email address and user profile are exempt from the "
            "trusted-user list and from the seven-day expiry of test-user authorizations [9]. "
            "(This corrects earlier advice.)",
        ],
        acceptance=[
            "Signing in with Google lands on the home page, signed in.",
            "The security log records login_succeeded with method google.",
        ],
        references=["[8]", "[9]"],
    ),
    Item(
        id="PE-006",
        title="Two credentials were exposed in a chat transcript",
        kind="Product risk",
        quality="Security",
        observed="31 Oct 2026",
        severity="High",
        priority="P1",
        likelihood=3,
        impact=4,
        status="Open",
        object="The Gemini API key and the Google OAuth client secret.",
        context="Both were pasted into an AI assistant conversation while setting up.",
        description=[
            "Both values now exist outside Vault and secrets/. Anyone with the transcript could "
            "spend the Gemini quota or act as this OAuth client.",
            "The OWASP Secrets Management Cheat Sheet: exposed keys should undergo immediate "
            "revocation; a replacement should be created and deployed; revoked secrets must be "
            "removed from the exposed system; and the secret's lifecycle should be logged [10].",
        ],
        expected="Credentials exist only in Vault and secrets/ (git-ignored, mode 600).",
        actual="Copies exist in a conversation history.",
        response="Mitigation",
        recommendation=[
            "Gemini: create a new key in AI Studio, write it to secrets/llm_api_key.txt, run "
            "make rotate-secret NAME=llm_api_key, check an episode runs, then delete the old key.",
            "Google: add a new client secret in Cloud Console, write it to "
            "secrets/google_client_secret.txt, run make rotate-secret NAME=google_client_secret, "
            "check Google sign-in, then delete the old secret.",
        ],
        acceptance=[
            "The old key and old secret no longer work.",
            "Episode generation and Google sign-in work with the new values.",
        ],
        references=["[10]"],
        progress=[
            "31 Oct 2026, located copies (values not printed): none in tracked files or in git "
            "history; none in shell history; secrets/ files are git-ignored with mode 600. One "
            "copy is in a local Claude Code conversation file under ~/.claude/projects/, which "
            "the owner may delete.",
            "31 Oct 2026: .env (holds POSTGRES_PASSWORD) restricted to mode 600.",
            "31 Oct 2026: added make rotate-secret NAME=..., which stores the new value from "
            "secrets/NAME.txt in Vault and restarts every service that reads secrets.",
            "Waiting on the owner: create the new Gemini key and Google client secret, run "
            "make rotate-secret for each, then delete the old ones with Google.",
        ],
    ),
    Item(
        id="PE-007",
        title="Accounts created with Google cannot delete themselves without a password reset",
        kind="Defect",
        quality="Interaction capability",
        observed="31 Oct 2026",
        severity="Low",
        priority="P3",
        likelihood=2,
        impact=2,
        status="Open",
        object="Account deletion (DELETE /v1/auth/me), which asks for the current password.",
        context="Design review of Google sign-in.",
        description=[
            "A Google-created account gets a random, unknown password. Deleting the account "
            "requires the current password, so the owner must first set one by password reset.",
        ],
        expected="Every account owner can delete their account directly.",
        actual="Google-only owners need a password reset first.",
        response="Mitigation",
        recommendation=[
            "Accept a fresh Google sign-in as confirmation for deletion, or document the "
            "reset-first path in the account page and docs/api.md.",
        ],
        acceptance=["A Google-only account can be deleted, or the page explains how."],
    ),
    Item(
        id="PE-008",
        title="Much of the recent work is not committed",
        kind="Project risk",
        quality="n/a (project)",
        observed="31 Oct 2026",
        severity="Medium",
        priority="P1",
        likelihood=3,
        impact=4,
        status="Open",
        object="Git working tree of branch include_ml_model.",
        context="git status on 31 Oct 2026.",
        description=[
            "42 paths are modified or new, including Google sign-in, the sign-in layout, the home "
            "page, the usage endpoint and this report. A lost working tree would lose them.",
        ],
        expected="Finished work is committed and pushed.",
        actual="42 uncommitted paths.",
        response="Mitigation",
        recommendation=[
            "Commit in logical steps (Google sign-in; sign-in layout; home page and usage "
            "endpoint; reports) and push the branch.",
        ],
        acceptance=["git status is clean and the branch is on the remote."],
    ),
    Item(
        id="PE-009",
        title="Failed and waiting episodes are left in the database",
        kind="Project risk",
        quality="n/a (project)",
        observed="31 Oct 2026",
        severity="Low",
        priority="P3",
        likelihood=2,
        impact=1,
        status="Open",
        object="episodes table.",
        context="Status counts on 31 Oct 2026: 9 published, 8 failed, 4 unchanged, 1 in review.",
        description=[
            "Three failures (89bc47c6, f6b9b53c, 96c07385) come from an ingest bug "
            "(name 'Section' is not defined) that has since been fixed. 99f22f5e has been "
            "waiting for approval since 22 October 2026.",
        ],
        expected="Only meaningful episodes remain; review decisions are made promptly.",
        actual="Stale failures and one pending review clutter the lists.",
        response="Mitigation",
        recommendation=["Retry or delete each failed episode; approve or reject 99f22f5e."],
        acceptance=["No failed episode older than a week remains without a note."],
    ),
    Item(
        id="PE-010",
        title="Monitoring reports the voice worker down while the host worker runs",
        kind="Defect",
        quality="Maintainability",
        observed="31 Oct 2026",
        severity="Low",
        priority="P3",
        likelihood=5,
        impact=1,
        status="Open",
        object="monitoring/prometheus.yml (scrapes voice:9100) and make voice-host.",
        context="Design review.",
        description=[
            "make voice-host stops the voice container that Prometheus scrapes at voice:9100, "
            "and the host worker serves metrics on port 9101 instead, so the voice target shows "
            "as down while voicing works.",
        ],
        expected="Monitoring reflects the worker that is actually running.",
        actual="A false down signal for the voice target.",
        response="Mitigation",
        recommendation=[
            "Add a scrape target for the host worker (host.docker.internal:9101), or label the "
            "Docker target as optional when the host worker is in use.",
        ],
        acceptance=["With make voice-host running, Prometheus shows a healthy voice target."],
    ),
    Item(
        id="PE-011",
        title="Voicing runs on one Mac GPU, about 12 minutes an episode",
        kind="Product risk",
        quality="Performance efficiency",
        observed="27 Oct 2026",
        severity="Low",
        priority="P3",
        likelihood=4,
        impact=2,
        status="Open",
        object="Chatterbox on the host worker (single process, Celery solo pool).",
        context="Re-voicing episode e03ee93c: 52 lines at about 11 to 15 seconds each.",
        description=[
            "One worker, one GPU: episodes are voiced one at a time. Acceptable for a prototype, "
            "but it does not scale to several users.",
        ],
        expected="Voicing time is known and stated.",
        actual="Not yet stated in the project documents.",
        response="Acceptance, with a contingency",
        recommendation=[
            "State the single-GPU constraint and the measured time in the project report.",
            "Contingency: Gemini speech when quota allows.",
        ],
        acceptance=["The report states the constraint and the measured figure."],
    ),
    Item(
        id="PE-012",
        title="Cloned speech may be slightly fast",
        kind="Product risk",
        quality="Interaction capability",
        observed="27 Oct 2026",
        severity="Low",
        priority="P3",
        likelihood=3,
        impact=2,
        status="Open",
        object="Chatterbox delivery settings (exaggeration, cfg_weight).",
        context="Episode e03ee93c: median pace 20.3 characters a second (range 11.0 to 25.8).",
        description=[
            "The pace has not been judged by listeners. Chatterbox's README notes that higher "
            "exaggeration tends to speed up speech and that reducing cfg_weight helps compensate "
            "with slower, more deliberate pacing [12].",
        ],
        expected="Listeners find the pace comfortable.",
        actual="Not yet assessed.",
        response="Mitigation",
        recommendation=[
            "After PE-004, listen; if rushed, lower cfg_weight in ChatterboxBackend.STYLES and "
            "bump STYLES_VERSION so lines are voiced again [12].",
        ],
        acceptance=["The owner judges the pace comfortable on a new episode."],
        references=["[12]"],
    ),
    Item(
        id="PE-013",
        title="Documentation drift: a misplaced TODO and outdated proposal wording",
        kind="Project risk",
        quality="Maintainability",
        observed="31 Oct 2026",
        severity="Low",
        priority="P3",
        likelihood=2,
        impact=2,
        status="Open",
        object="api/controllers/auth_controller.py line 146; the project proposal.",
        context="Code and document review.",
        description=[
            "A TODO about segments per episode sits in the sign-in controller, unrelated to it. "
            "The proposal's wording about the number of workers no longer matches the stack.",
        ],
        expected="Notes sit with the code they concern; documents match the system.",
        actual="One stray TODO; one outdated passage.",
        response="Mitigation",
        recommendation=[
            "Move the TODO into this register or the pipeline code; update the proposal."
        ],
        acceptance=["No unrelated TODO remains in auth_controller.py; the proposal matches."],
    ),
]

REFERENCES = [
    (
        "[1]",
        "International Software Testing Qualifications Board. Certified Tester Foundation "
        "Level Syllabus, v4.0.1, 15 September 2024. Sections 5.2 (Risk Management) and 5.5 "
        "(Defect Management).",
        "https://www.istqb.org/wp-content/uploads/2024/11/ISTQB_CTFL_Syllabus_v4.0.1.pdf",
    ),
    (
        "[2]",
        "ISO/IEC/IEEE 29119-3:2021, Software and systems engineering - Software testing - "
        "Part 3: Test documentation, 2nd edition, October 2021. Normative text not consulted; "
        "its report fields are taken from [1], which cites it.",
        "https://webstore.iec.ch/publication/71834",
    ),
    (
        "[3]",
        "ISO/IEC 25010:2023, Systems and software engineering - Systems and software "
        "Quality Requirements and Evaluation (SQuaRE) - Product quality model. Normative text not "
        "consulted; characteristic names taken from [4] and [5].",
        "https://www.iso.org/standard/78176.html",
    ),
    (
        "[4]",
        "G. Starke, arc42 Quality Model: ISO/IEC 25010 and its 2023 update.",
        "https://quality.arc42.org/standards/iso-25010",
    ),
    (
        "[5]",
        "Sonar. Understanding ISO/IEC 25010: framework for software quality.",
        "https://www.sonarsource.com/resources/library/iso-iec-25010-explained/",
    ),
    (
        "[6]",
        "ISO 31000:2018, Risk management - Guidelines. Referenced by [1], section 5.2; "
        "normative text not consulted.",
        "https://www.iso.org/standard/65694.html",
    ),
    (
        "[7]",
        "Google AI for Developers. Gemini API: Rate limits.",
        "https://ai.google.dev/gemini-api/docs/rate-limits",
    ),
    (
        "[8]",
        "Google for Developers. Using OAuth 2.0 for Web Server Applications.",
        "https://developers.google.com/identity/protocols/oauth2/web-server",
    ),
    (
        "[9]",
        "Google Cloud Platform Console Help. Manage App Audience.",
        "https://support.google.com/cloud/answer/15549945",
    ),
    (
        "[10]",
        "OWASP Cheat Sheet Series. Secrets Management Cheat Sheet, sections 2.7 and 9.2.",
        "https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html",
    ),
    (
        "[11]",
        "Docker Docs. Using profiles with Compose.",
        "https://docs.docker.com/compose/how-tos/profiles/",
    ),
    (
        "[12]",
        "Resemble AI. Chatterbox (README, MIT licence).",
        "https://github.com/resemble-ai/chatterbox",
    ),
]

# ---- layout ---------------------------------------------------------------------------------
ACCENT = colors.HexColor("#9a3412")
INK = colors.HexColor("#1c1917")
MUTED = colors.HexColor("#57534e")
RULE = colors.HexColor("#d6d3d1")
SHADE = colors.HexColor("#f5f5f4")
BANDS = {
    "Low": colors.HexColor("#dcfce7"),
    "Medium": colors.HexColor("#fef9c3"),
    "High": colors.HexColor("#fed7aa"),
    "Very high": colors.HexColor("#fecaca"),
}

base = getSampleStyleSheet()
BODY = ParagraphStyle(
    "body",
    parent=base["BodyText"],
    fontName="Helvetica",
    fontSize=9.5,
    leading=13.5,
    textColor=INK,
    alignment=TA_LEFT,
    spaceAfter=4,
)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8.5, leading=11.5)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=8.5, leading=11, spaceAfter=0)
CELL_B = ParagraphStyle("cellb", parent=CELL, fontName="Helvetica-Bold")
H1 = ParagraphStyle(
    "h1",
    parent=BODY,
    fontName="Helvetica-Bold",
    fontSize=15,
    leading=19,
    textColor=ACCENT,
    spaceBefore=6,
    spaceAfter=8,
)
H2 = ParagraphStyle(
    "h2",
    parent=BODY,
    fontName="Helvetica-Bold",
    fontSize=11.5,
    leading=15,
    textColor=INK,
    spaceBefore=10,
    spaceAfter=5,
)
BULLET = ParagraphStyle("bullet", parent=BODY, leftIndent=12, bulletIndent=2)


def p(text: str, style: ParagraphStyle = BODY) -> Paragraph:
    return Paragraph(text, style)


def bullets(lines: list[str], style: ParagraphStyle = BULLET) -> list[Paragraph]:
    return [Paragraph(line, style, bulletText="•") for line in lines]


def grid(rows: list[list], widths: list[float], header: bool = True, extra=()) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.5, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), SHADE)]
    table.setStyle(TableStyle(style + list(extra)))
    return table


def cells(values: list[str], bold: bool = False) -> list[Paragraph]:
    return [Paragraph(v, CELL_B if bold else CELL) for v in values]


def on_page(canvas, doc) -> None:
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, height - 14 * mm, width - 18 * mm, height - 14 * mm)
    canvas.line(18 * mm, 14 * mm, width - 18 * mm, 14 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, height - 12 * mm, f"{SYSTEM} - {TITLE}")
    canvas.drawRightString(width - 18 * mm, height - 12 * mm, f"{DOC_ID}  v{VERSION}")
    canvas.drawString(18 * mm, 10 * mm, f"Issued {ISSUED}")
    canvas.drawRightString(width - 18 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def cover() -> list:
    story: list = [Spacer(1, 40 * mm)]
    story.append(
        p(
            SYSTEM.upper(),
            ParagraphStyle(
                "k", parent=BODY, fontName="Helvetica-Bold", fontSize=10, textColor=ACCENT
            ),
        )
    )
    story.append(p(TITLE, ParagraphStyle("t", parent=H1, fontSize=28, leading=34, textColor=INK)))
    story.append(
        p(
            "Problems found, their risk, and what to do about each, in the structure of "
            "a defect report (ISO/IEC/IEEE 29119-3, via the ISTQB syllabus) and a risk "
            "register (ISO 31000).",
            ParagraphStyle("s", parent=BODY, fontSize=11, leading=15, textColor=MUTED),
        )
    )
    story.append(Spacer(1, 14 * mm))
    meta = [
        ["Document ID", DOC_ID],
        ["Version", VERSION],
        ["Issued", ISSUED],
        ["Status", "Issued for action"],
        ["System", f"{SYSTEM} (COMP 5112 project artifact)"],
        ["Owner", "Ayomide Omotosho, project owner and developer"],
        ["Prepared by", "Claude (Anthropic), AI coding assistant, at the owner's request"],
        [
            "Items",
            f"{len(ITEMS)}: "
            f"{sum(i.kind == 'Defect' for i in ITEMS)} defects, "
            f"{sum(i.kind == 'Product risk' for i in ITEMS)} product risks, "
            f"{sum(i.kind == 'Project risk' for i in ITEMS)} project risks",
        ],
    ]
    story.append(
        grid(
            [cells([k], True) + cells([v]) for k, v in meta],
            [38 * mm, 128 * mm],
            header=False,
            extra=[("BACKGROUND", (0, 0), (0, -1), SHADE)],
        )
    )
    story.append(Spacer(1, 8 * mm))
    story.append(p("Revision history", H2))
    story.append(
        grid(
            [cells(["Version", "Date", "Change"], True)] + [cells(list(r)) for r in REVISIONS],
            [20 * mm, 26 * mm, 120 * mm],
        )
    )
    story.append(PageBreak())
    return story


def summary_page() -> list:
    story: list = [p("1. Summary", H1)]
    high = [i for i in ITEMS if band(i.level) in ("High", "Very high")]
    story.append(
        p(
            f"The review of 31 October 2026 recorded {len(ITEMS)} items. {len(high)} rate High "
            "or Very high and should be handled first: the Docker voice worker taking jobs it "
            "cannot run (PE-001), the exposed credentials (PE-006), the uncommitted work "
            "(PE-008), the Google redirect URI (PE-005) and the shared Gemini quota (PE-002). The "
            "register below lists every item; section 6 gives each one in full. Since the first "
            "issue, PE-001 has been fixed and awaits its last confirmation test (an episode "
            "voiced end to end)."
        )
    )
    story.append(Spacer(1, 3 * mm))
    rows = [
        cells(
            ["ID", "Title", "Type", "ISO/IEC 25010", "Sev.", "Pri.", "Risk (L x I)", "Status"], True
        )
    ]
    extra = []
    for n, item in enumerate(sorted(ITEMS, key=lambda i: (-i.level, i.priority, i.id)), start=1):
        rows.append(
            cells(
                [
                    item.id,
                    item.title,
                    item.kind,
                    item.quality,
                    item.severity,
                    item.priority,
                    f"{band(item.level)} ({item.likelihood} x {item.impact} = {item.level})",
                    item.status,
                ]
            )
        )
        extra.append(("BACKGROUND", (6, n), (6, n), BANDS[band(item.level)]))
    story.append(
        grid(
            rows,
            [14 * mm, 41 * mm, 18 * mm, 22 * mm, 15 * mm, 9 * mm, 27 * mm, 20 * mm],
            extra=extra,
        )
    )
    story.append(
        p(
            "Sorted by risk level, then priority. Sev. = severity; Pri. = priority; "
            "L = likelihood; I = impact (section 4).",
            SMALL,
        )
    )
    return story


def method() -> list:
    story: list = [PageBreak(), p("2. Purpose and scope", H1)]
    story.append(
        p(
            "This report records the problems found in the AI Podcast Engine on 31 October "
            "2026, rates each by severity, priority and risk, and recommends a response with "
            "criteria for confirming it is resolved. It is a working document: items are worked "
            "through one at a time and the register is re-issued as their status changes."
        )
    )
    story.append(p(f"<b>Test object and environment.</b> {ENV}"))
    story.append(
        p(
            "<b>How the items were found.</b> Inspection of the running stack (service health, "
            "worker logs, the episodes table, Redis budget counters), reproduction of failures, "
            "code and configuration review, and live checks of external services (Google OAuth)."
        )
    )
    story.append(p("3. Standards and sources applied", H1))
    story.append(
        p(
            "The structure follows published guidance. Where a standard's normative text is "
            "sold and was not consulted, this report relies on a public source that quotes or "
            "summarises it, and says so."
        )
    )
    rows = [cells(["Source", "What this report takes from it"], True)]
    rows += [
        cells(
            [
                "ISTQB CTFL Syllabus v4.0.1, section 5.5 [1], citing ISO/IEC/IEEE 29119-3 [2]",
                "The fields of each defect report: unique identifier; title; date observed, "
                "issuing organization and author with role; test object and environment; "
                "context; description enabling reproduction; expected and actual results; "
                "severity (degree of impact); priority to fix; status; references. Status values "
                "come from its list: open, deferred, duplicate, waiting to be fixed, awaiting "
                "confirmation testing, re-opened, closed, rejected.",
            ]
        ),
        cells(
            [
                "ISTQB CTFL Syllabus v4.0.1, section 5.2 [1], citing ISO 31000 [6]",
                "Risk is characterised by risk likelihood and risk impact, which together express "
                "the risk level; in the quantitative approach the level is their product, in the "
                "qualitative approach a risk matrix. The split into project risks and product "
                "risks, and the response options: mitigation, acceptance, transfer, contingency.",
            ]
        ),
        cells(
            [
                "ISO/IEC 25010:2023 [3], names as given in [4] and [5]",
                "Each defect and product risk is classified by the product quality characteristic "
                "it affects: functional suitability, performance efficiency, compatibility, "
                "interaction capability, reliability, security, maintainability, flexibility, "
                "safety. ISTQB relates product risks to this model [1].",
            ]
        ),
        cells(
            [
                "Vendor and community documentation [7]-[12]",
                "Facts behind specific recommendations (quota rules, OAuth behaviour, secret "
                "handling, Compose profiles, Chatterbox tuning), cited in each item.",
            ]
        ),
    ]
    story.append(grid(rows, [52 * mm, 114 * mm]))
    return story


def scales() -> list:
    story: list = [p("4. Rating scales", H1)]
    story.append(
        p(
            "The sources define what each rating is, not the scale itself, so the scales below are "
            "this project's. Severity is the degree of impact on stakeholders or requirements; "
            "priority is the order of fixing [1]."
        )
    )
    story.append(
        grid(
            [
                cells(["Severity", "Meaning in this project"], True),
                cells(
                    [
                        "Critical",
                        "Core function unusable with no workaround, or data or security "
                        "compromised.",
                    ]
                ),
                cells(
                    [
                        "High",
                        "A core function fails, or a security exposure exists; a workaround "
                        "exists.",
                    ]
                ),
                cells(["Medium", "A secondary function fails or degrades; a workaround exists."]),
                cells(["Low", "Cosmetic, documentation or housekeeping."]),
            ],
            [24 * mm, 142 * mm],
        )
    )
    story.append(Spacer(1, 3 * mm))
    story.append(
        grid(
            [
                cells(["Priority", "Meaning in this project"], True),
                cells(["P1", "Fix before the next episode is generated or the system is shown."]),
                cells(["P2", "Fix in the current piece of work."]),
                cells(["P3", "Fix when convenient."]),
            ],
            [24 * mm, 142 * mm],
        )
    )
    story.append(Spacer(1, 3 * mm))
    matrix: list = []
    matrix.append(
        p(
            "<b>Risk level</b> = likelihood (1 to 5) x impact (1 to 5), the quantitative approach "
            "in [1]. Bands: 1-4 Low, 5-9 Medium, 10-16 High, 20-25 Very high. The labels below are "
            "this project's choice, not taken from ISO 31000."
        )
    )
    header = [p("<b>Likelihood \\ Impact</b>", CELL)] + [
        p(f"<b>{n + 1}</b> {name}", CELL) for n, name in enumerate(IMPACT)
    ]
    rows = [header]
    extra = []
    for li in range(5, 0, -1):
        row = [p(f"<b>{li}</b> {LIKELIHOOD[li - 1]}", CELL)]
        for im in range(1, 6):
            level = li * im
            ids = [i.id for i in ITEMS if i.likelihood == li and i.impact == im]
            row.append(p(f"<b>{level}</b><br/>{' '.join(ids)}", CELL))
            extra.append(("BACKGROUND", (im, 6 - li), (im, 6 - li), BANDS[band(level)]))
        rows.append(row)
    matrix.append(grid(rows, [36 * mm] + [26 * mm] * 5, extra=extra))
    matrix.append(p("Each cell shows its risk level and the items rated there.", SMALL))
    story.append(KeepTogether(matrix))
    return story


def detail(item: Item) -> list:
    head = p(f"{item.id}  {item.title}", H2)
    facts = [
        ("Identifier", item.id),
        ("Type", item.kind),
        ("Quality characteristic", item.quality),
        ("Date observed", item.observed),
        ("Reported by", "Claude (AI coding assistant) for Ayomide Omotosho (project owner)"),
        ("Test object", item.object),
        ("Environment", ENV),
        ("Context", item.context),
        ("Severity / priority", f"{item.severity} / {item.priority}"),
        (
            "Risk",
            f"Likelihood {item.likelihood} ({LIKELIHOOD[item.likelihood - 1]}) x impact "
            f"{item.impact} ({IMPACT[item.impact - 1]}) = {item.level}, "
            f"{band(item.level)}",
        ),
        ("Status", item.status),
        ("Response", item.response),
    ]
    table = grid(
        [cells([k], True) + cells([v]) for k, v in facts],
        [38 * mm, 128 * mm],
        header=False,
        extra=[
            ("BACKGROUND", (0, 0), (0, -1), SHADE),
            ("BACKGROUND", (1, 9), (1, 9), BANDS[band(item.level)]),
        ],
    )
    body: list = [p("<b>Description</b>"), *bullets(item.description)]
    body += [p(f"<b>Expected:</b> {item.expected}"), p(f"<b>Actual:</b> {item.actual}")]
    body += [p("<b>Recommendation</b>"), *bullets(item.recommendation)]
    body += [p("<b>Resolved when</b>"), *bullets(item.acceptance)]
    if item.progress:
        body += [p("<b>Progress</b>"), *bullets(item.progress)]
    if item.references:
        body.append(p(f"<b>References:</b> {', '.join(item.references)} (section 8)", SMALL))
    return [KeepTogether([head, table, Spacer(1, 2 * mm)]), *body, Spacer(1, 4 * mm)]


def plan() -> list:
    story: list = [PageBreak(), p("7. Treatment order", H1)]
    story.append(
        p(
            "Work proceeds one item at a time, highest risk and priority first. Re-issue this "
            'report when an item changes status; an item is closed only when every "resolved '
            'when" criterion has been checked.'
        )
    )
    order = sorted(ITEMS, key=lambda i: (i.priority, -i.level, i.id))
    rows = [cells(["Step", "Item", "Priority", "Risk", "First action"], True)]
    for n, item in enumerate(order, start=1):
        rows.append(
            cells(
                [
                    str(n),
                    f"{item.id} {item.title}",
                    item.priority,
                    f"{band(item.level)} ({item.level})",
                    item.recommendation[0],
                ]
            )
        )
    story.append(grid(rows, [10 * mm, 52 * mm, 14 * mm, 20 * mm, 70 * mm]))
    return story


def references() -> list:
    story: list = [p("8. References", H1)]
    story.append(p("All web sources were accessed on 31 October 2026.", SMALL))
    for ref, text, url in REFERENCES:
        story.append(
            p(
                f"<b>{ref}</b> {text} <font color='#9a3412'>{url}</font>",
                ParagraphStyle(
                    "ref", parent=SMALL, leftIndent=16, firstLineIndent=-16, spaceAfter=5
                ),
            )
        )
    return story


def build() -> Path:
    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=f"{SYSTEM} - {TITLE}",
        author="Ayomide Omotosho",
        subject=f"{DOC_ID} v{VERSION}",
        creator="docs/reports/defect_risk_report.py",
    )
    story = cover() + summary_page() + method() + scales()
    story += [PageBreak(), p("5. Classification of items", H1)]
    rows = [cells(["Type", "Items"], True)]
    for kind in ("Defect", "Product risk", "Project risk"):
        rows.append(cells([kind, ", ".join(i.id for i in ITEMS if i.kind == kind)]))
    story.append(grid(rows, [30 * mm, 136 * mm]))
    story.append(Spacer(1, 3 * mm))
    rows = [cells(["ISO/IEC 25010:2023 characteristic", "Items"], True)]
    for quality in dict.fromkeys(i.quality for i in ITEMS):
        rows.append(cells([quality, ", ".join(i.id for i in ITEMS if i.quality == quality)]))
    story.append(grid(rows, [56 * mm, 110 * mm]))
    story += [PageBreak(), p("6. Item reports", H1)]
    for item in ITEMS:
        story += detail(item)
    story += plan() + references()
    doc.build(story, onLaterPages=on_page)  # the cover has no header or footer
    return OUT


if __name__ == "__main__":
    print(build())  # noqa: T201 - the command's output
