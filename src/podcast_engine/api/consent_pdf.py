"""The voice consent form as a PDF, rendered from the same sections the web app shows.

The PDF can be downloaded, read in full, and printed: for someone else's voice, the speaker can
sign the printed copy, and the account holder keeps it as the written permission the form asks
about. Rendered once per process; the text changes only with CONSENT_VERSION.
"""

from functools import lru_cache
from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape

from podcast_engine.api.models.voices_model import CONSENT_SECTIONS, CONSENT_TITLE, CONSENT_VERSION

ACCENT = "#9a3412"
FILENAME = f"voice-consent-form-{CONSENT_VERSION}.pdf"


@lru_cache(maxsize=1)
def consent_pdf() -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table

    body = ParagraphStyle("body", fontName="Helvetica", fontSize=10, leading=14.5, spaceAfter=5)
    heading = ParagraphStyle(
        "heading", parent=body, fontName="Helvetica-Bold", fontSize=11.5, leading=15,
        spaceBefore=9, spaceAfter=4,
    )  # fmt: skip
    title = ParagraphStyle(
        "title", parent=body, fontName="Helvetica-Bold", fontSize=18, leading=22,
        textColor=colors.HexColor(ACCENT), spaceAfter=4,
    )  # fmt: skip
    small = ParagraphStyle("small", parent=body, fontSize=8.5, leading=11, textColor=colors.grey)
    bullet = ParagraphStyle("bullet", parent=body, leftIndent=12, bulletIndent=2, spaceAfter=3)

    story: list[Any] = [
        Paragraph(CONSENT_TITLE, title),
        Paragraph(f"Podcast Engine · version {CONSENT_VERSION}", small),
        Spacer(1, 4 * mm),
    ]
    for section, paragraphs in CONSENT_SECTIONS:
        blocks = [
            Paragraph(escape(text[2:]), bullet, bulletText="\u2022")
            if text.startswith("- ")
            else Paragraph(escape(text), body)
            for text in paragraphs
        ]
        story.append(KeepTogether([Paragraph(section, heading), blocks[0]]))
        story += blocks[1:]

    line = "_" * 38
    fields = [
        ["Speaker's full name", line],
        ["Speaker's signature", line],
        ["Date", line],
        ["Speaker's contact (optional)", line],
        ["Whose voice", "[ ] my own voice&nbsp;&nbsp;&nbsp;[ ] used with written permission"],
        ["Terms of use: limits the speaker sets", line],
        ["", line],
        ["Account holder's name", line],
        ["Account holder's contact", line],
        ["Account holder's signature", line],
        ["For someone else's voice: where this signed copy is kept", line],
    ]
    signatures = Table(
        [[Paragraph(label, body), Paragraph(blank, body)] for label, blank in fields],
        colWidths=[70 * mm, 100 * mm],
    )
    story += [
        Spacer(1, 6 * mm),
        KeepTogether([Paragraph("Signatures", heading), signatures]),
        Spacer(1, 6 * mm),
        Paragraph(
            "In Podcast Engine this form is signed by typing the signer's name; the version and "
            "full text of the form are stored with the recording. A printed and signed copy can "
            "serve as the written permission for someone else's voice.",
            small,
        ),
    ]

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.grey)
        canvas.drawString(20 * mm, 12 * mm, f"{CONSENT_TITLE}, version {CONSENT_VERSION}")
        canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, f"Page {doc.page}")
        canvas.restoreState()

    out = BytesIO()
    SimpleDocTemplate(
        out, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm,
        bottomMargin=20 * mm, title=f"{CONSENT_TITLE} ({CONSENT_VERSION})",
        author="Podcast Engine", subject="Consent to record and clone a voice",
    ).build(story, onFirstPage=footer, onLaterPages=footer)  # fmt: skip
    return out.getvalue()
