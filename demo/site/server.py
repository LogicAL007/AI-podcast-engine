"""A news page that changes on demand, as a show source for demonstrating refresh (FR8).

    make demo-site            # starts it in the stack: http://localhost:8095 in the browser
    make demo-next            # publishes the next edition (or use the button on the page)
    make demo-reset           # back to edition 1

The pipeline's workers reach it as http://demo-site:8095/ inside the stack; that is the URL to
give a show. The page is fictional and says so. Only the <article> holds the story, so the
edition controls above it are never read as a source. Each change of edition sets the page's
modified time to now, as a real news site would. Standard library only; state is in memory, so a
restart goes back to edition 1.
"""

import os
import threading
from datetime import UTC, datetime
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from editions import EDITIONS, TITLE

PORT = int(os.environ.get("DEMO_SITE_PORT", "8095"))
STYLE = """
body { font: 17px/1.6 Georgia, serif; margin: 0; background: #f7f5f0; color: #1d1d1b; }
.demo { font: 14px/1.4 system-ui, sans-serif; background: #1d3557; color: #fff; }
.demo { padding: 12px 16px; }
.demo form { display: inline; margin-left: 8px; }
.demo button { font: inherit; padding: 4px 10px; border-radius: 6px; border: 0; }
.demo button:disabled { opacity: .5; }
.masthead { text-align: center; border-bottom: 3px double #1d1d1b; padding: 16px; }
.masthead p { margin: 0; font: 13px system-ui, sans-serif; color: #555; }
article { max-width: 680px; margin: 0 auto; padding: 16px; }
h1 { line-height: 1.2; }
"""


class Story:
    """Which edition is live, and since when."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.index = 0
        self.changed = datetime.now(UTC)

    def move(self, index: int) -> None:
        with self._lock:
            index = max(0, min(index, len(EDITIONS) - 1))
            if index != self.index:
                self.index, self.changed = index, datetime.now(UTC)


def anchor(heading: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in heading.lower()).strip("-")


def render(story: Story) -> str:
    edition = EDITIONS[story.index]
    stamp = story.changed.isoformat(timespec="seconds")
    sections = "".join(
        f'<h2 id="{anchor(heading)}">{escape(heading)}</h2>'
        + "".join(f"<p>{escape(p)}</p>" for p in paragraphs)
        for heading, paragraphs in edition["sections"]
    )
    last = story.index == len(EDITIONS) - 1
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(TITLE)} | The Port Arden Ledger</title>
<meta property="article:modified_time" content="{stamp}">
<style>{STYLE}</style></head>
<body>
<header class="demo" aria-label="Demo controls">
  <strong>Demo site (fictional).</strong> {escape(edition["label"])}, live since {stamp}.
  {escape(edition["change"])}
  <form method="post" action="/next">
    <button {"disabled" if last else ""}>Publish next edition</button>
  </form>
  <form method="post" action="/reset"><button>Reset to edition 1</button></form>
</header>
<div class="masthead"><h2>The Port Arden Ledger</h2>
<p>A fictional local paper, made to demonstrate Podcast Engine's refresh.</p></div>
<article>
<h1>{escape(TITLE)}</h1>
{sections}
</article>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    story = Story()

    def _send(self, status: HTTPStatus, body: str = "", location: str = "") -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        if location:
            self.send_header("Location", location)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._send(HTTPStatus.OK, "ok")
        elif self.path in ("/", "/index.html"):
            self._send(HTTPStatus.OK, render(self.story))
        else:
            self._send(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        if self.path == "/next":
            self.story.move(self.story.index + 1)
        elif self.path == "/reset":
            self.story.move(0)
        else:
            self._send(HTTPStatus.NOT_FOUND, "Not found")
            return
        self._send(HTTPStatus.SEE_OTHER, location="/")


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()  # noqa: S104 - inside the stack
