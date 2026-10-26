"""A small toolkit for drawing clean architecture diagrams as standalone SVG.

Boxes, data-store cylinders, people, groups, orthogonal arrows with rounded corners, chips,
sequence-diagram lifelines and entity tables, all in one visual language. Every text is measured
against the space it has, and `Diagram.save` refuses to write a diagram whose labels would spill.
Standard library only.
"""

from __future__ import annotations

import html
import math
from dataclasses import dataclass
from pathlib import Path

FONT = "'Helvetica Neue', Helvetica, Arial, sans-serif"
MONO = "'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace"

INK = "#1C1917"
MUTED = "#57534E"
FAINT = "#A8A29E"
RULE = "#D6D3D1"
PANEL = "#FAFAF9"
WHITE = "#FFFFFF"
ACCENT = "#C2410C"  # the web app's dark orange

# kind -> (fill, stroke)
KINDS: dict[str, tuple[str, str]] = {
    "person": ("#F5F5F4", "#78716C"),
    "client": ("#F5F5F4", "#78716C"),
    "system": ("#FFF4EC", ACCENT),
    "edge": ("#FFF4EC", ACCENT),
    "service": ("#EEF3F9", "#335C8A"),
    "worker": ("#EEF6F2", "#2E6B5E"),
    "store": ("#F3F1F8", "#5B4B8A"),
    "security": ("#FDF6E3", "#946200"),
    "external": (WHITE, "#78716C"),
    "support": ("#F1F5F9", "#475569"),
    "note": (PANEL, RULE),
    "plain": (WHITE, RULE),
    "danger": ("#FEF2F2", "#B91C1C"),
    "success": ("#F0FDF4", "#15803D"),
}

KIND_NAMES = {
    "person": "Person",
    "client": "Client",
    "system": "This system",
    "edge": "Edge (nginx)",
    "service": "Application service",
    "worker": "Pipeline worker",
    "store": "Data store",
    "security": "Security service",
    "external": "External system",
    "support": "Supporting service",
}


def text_width(text: str, size: float, *, bold: bool = False, mono: bool = False) -> float:
    """A conservative estimate of rendered width, close enough to keep labels inside shapes."""
    if mono:
        return len(text) * size * 0.62
    units = 0.0
    for ch in text:
        if ch in "iljI.,:;'|!()[]{} /`":
            units += 0.31
        elif ch in "mwMW@%":
            units += 0.86
        elif ch.isupper():
            units += 0.67
        elif ch.isdigit():
            units += 0.56
        elif ch in "→−–—…·":
            units += 0.62
        else:
            units += 0.53
    return units * size * (1.07 if bold else 1.0)


def esc(text: str) -> str:
    return html.escape(text, quote=True)


@dataclass
class Box:
    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    @property
    def r(self) -> float:
        return self.x + self.w

    @property
    def b(self) -> float:
        return self.y + self.h

    def left(self, t: float = 0.5) -> tuple[float, float]:
        return (self.x, self.y + self.h * t)

    def right(self, t: float = 0.5) -> tuple[float, float]:
        return (self.r, self.y + self.h * t)

    def top(self, t: float = 0.5) -> tuple[float, float]:
        return (self.x + self.w * t, self.y)

    def bottom(self, t: float = 0.5) -> tuple[float, float]:
        return (self.x + self.w * t, self.b)


def _rounded_path(points: list[tuple[float, float]], radius: float = 7) -> str:
    out = [f"M{points[0][0]:.1f},{points[0][1]:.1f}"]
    for i in range(1, len(points) - 1):
        (x0, y0), (x1, y1), (x2, y2) = points[i - 1], points[i], points[i + 1]
        l1 = math.hypot(x1 - x0, y1 - y0)
        l2 = math.hypot(x2 - x1, y2 - y1)
        rr = min(radius, l1 / 2, l2 / 2)
        if l1 == 0 or l2 == 0:
            continue
        ax, ay = x1 - (x1 - x0) / l1 * rr, y1 - (y1 - y0) / l1 * rr
        bx, by = x1 + (x2 - x1) / l2 * rr, y1 + (y2 - y1) / l2 * rr
        out.append(f"L{ax:.1f},{ay:.1f} Q{x1:.1f},{y1:.1f} {bx:.1f},{by:.1f}")
    out.append(f"L{points[-1][0]:.1f},{points[-1][1]:.1f}")
    return " ".join(out)


class Diagram:
    def __init__(
        self,
        slug: str,
        number: int,
        total: int,
        title: str,
        subtitle: str,
        *,
        w: int = 1600,
        h: int = 900,
    ) -> None:
        self.slug, self.number, self.total = slug, number, total
        self.title, self.subtitle = title, subtitle
        self.w, self.h = w, h
        self.body: list[str] = []
        self.problems: list[str] = []
        self.markers: set[str] = set()

    # ---- primitives --------------------------------------------------------------------------
    def add(self, svg: str) -> None:
        self.body.append(svg)

    def text(
        self,
        x: float,
        y: float,
        value: str,
        *,
        size: float = 12,
        color: str = INK,
        bold: bool = False,
        mono: bool = False,
        anchor: str = "start",
        maxw: float | None = None,
        italic: bool = False,
        spacing: float = 0,
    ) -> float:
        width = text_width(value, size, bold=bold, mono=mono) + spacing * len(value)
        if maxw is not None and width > maxw + 0.5:
            self.problems.append(f"{self.slug}: {value!r} needs {width:.0f}px, has {maxw:.0f}px")
        family = MONO if mono else FONT
        extra = ' font-weight="700"' if bold else ""
        extra += ' font-style="italic"' if italic else ""
        extra += f' letter-spacing="{spacing}"' if spacing else ""
        self.add(
            f'<text x="{x:.1f}" y="{y:.1f}" font-family="{family}" font-size="{size}" '
            f'fill="{color}" text-anchor="{anchor}"{extra}>{esc(value)}</text>'
        )
        return width

    def rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        fill: str = WHITE,
        stroke: str = RULE,
        sw: float = 1.4,
        rx: float = 10,
        dashed: bool = False,
        shadow: bool = False,
    ) -> None:
        dash = ' stroke-dasharray="6 4"' if dashed else ""
        filt = ' filter="url(#shadow)"' if shadow else ""
        self.add(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{dash}{filt}/>'
        )

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        *,
        color: str = RULE,
        sw: float = 1,
        dashed: bool = False,
    ) -> None:
        dash = ' stroke-dasharray="4 4"' if dashed else ""
        self.add(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="{sw}"{dash}/>'
        )

    # ---- shapes ------------------------------------------------------------------------------
    def box(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        title: str | None = None,
        tech: str | None = None,
        lines: list[str] | tuple[str, ...] = (),
        *,
        kind: str = "service",
        badge: str | None = None,
        align: str = "left",
        title_size: float = 14,
        line_size: float = 12,
        mono_lines: bool = False,
        icon: str | None = None,
        dashed: bool | None = None,
        rx: float = 10,
        pad: float = 14,
        title_color: str = INK,
    ) -> Box:
        fill, stroke = KINDS[kind]
        if dashed is None:
            dashed = kind == "external"
        self.rect(
            x,
            y,
            w,
            h,
            fill=fill,
            stroke=stroke,
            dashed=dashed,
            shadow=kind not in ("note", "plain"),
            rx=rx,
        )
        if icon == "cylinder":
            pass
        self._box_text(x, y, w, h, title, tech, lines, stroke=stroke, badge=badge, align=align,
                       title_size=title_size, line_size=line_size, mono_lines=mono_lines, icon=icon,
                       pad=pad, top=y, title_color=title_color)  # fmt: skip
        return Box(x, y, w, h)

    def _box_text(
        self, x, y, w, h, title, tech, lines, *, stroke, badge, align, title_size, line_size,
        mono_lines, icon, pad, top, title_color,
    ) -> None:  # fmt: skip
        inner = w - 2 * pad
        cursor = top + pad + title_size - 2
        tx = x + pad
        offset = 0.0
        if badge or icon == "person":
            offset = 26
        if title:
            if align == "center":
                total = text_width(title, title_size, bold=True) + offset
                start = x + (w - total) / 2
                if badge:
                    self._badge(start + 10, cursor - title_size * 0.36, badge, stroke)
                if icon == "person":
                    self._person(start + 10, cursor - title_size * 0.36, stroke)
                self.text(
                    start + offset,
                    cursor,
                    title,
                    size=title_size,
                    bold=True,
                    color=title_color,
                    maxw=inner - offset,
                )
            else:
                if badge:
                    self._badge(tx + 10, cursor - title_size * 0.36, badge, stroke)
                if icon == "person":
                    self._person(tx + 10, cursor - title_size * 0.36, stroke)
                self.text(
                    tx + offset,
                    cursor,
                    title,
                    size=title_size,
                    bold=True,
                    color=title_color,
                    maxw=inner - offset,
                )
        if tech:
            cursor += 18
            self._line_text(x, w, pad, cursor, tech, 11.5, MUTED, align, mono=False)
        if lines:
            cursor += 21 if (title or tech) else 0
            for i, value in enumerate(lines):
                if i:
                    cursor += line_size * 1.42
                self._line_text(x, w, pad, cursor, value, line_size, INK, align, mono=mono_lines)
        if cursor + pad - 4 > y + h:
            self.problems.append(
                f"{self.slug}: box {title!r} needs height {cursor + pad - 4 - y:.0f}, has {h:.0f}"
            )

    def _line_text(self, x, w, pad, y, value, size, color, align, *, mono) -> None:
        inner = w - 2 * pad
        spaces = len(value) - len(value.lstrip(" "))
        if spaces and align != "center":
            indent = spaces * size * 0.45
            self.text(
                x + pad + indent,
                y,
                value.lstrip(" "),
                size=size,
                color=color,
                maxw=inner - indent,
                mono=mono,
            )
            return
        if align == "center":
            self.text(
                x + w / 2, y, value, size=size, color=color, anchor="middle", maxw=inner, mono=mono
            )
        else:
            self.text(x + pad, y, value, size=size, color=color, maxw=inner, mono=mono)

    def _badge(self, cx: float, cy: float, value: str, color: str) -> None:
        self.add(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="10" fill="{color}"/>')
        self.text(cx, cy + 4, value, size=11, bold=True, color=WHITE, anchor="middle")

    def _person(self, cx: float, cy: float, color: str) -> None:
        self.add(
            f'<circle cx="{cx:.1f}" cy="{cy - 4:.1f}" r="4.5" fill="{color}"/>'
            f'<path d="M{cx - 8:.1f},{cy + 9:.1f} Q{cx:.1f},{cy - 4:.1f} {cx + 8:.1f},{cy + 9:.1f} Z" fill="{color}"/>'
        )

    def cylinder(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        title: str,
        tech: str | None = None,
        lines: list[str] | tuple[str, ...] = (),
        *,
        kind: str = "store",
        align: str = "left",
        title_size: float = 14,
        line_size: float = 12,
    ) -> Box:
        fill, stroke = KINDS[kind]
        ry = 9
        body = (
            f"M{x:.1f},{y + ry:.1f} A{w / 2:.1f},{ry} 0 0 1 {x + w:.1f},{y + ry:.1f} "
            f"L{x + w:.1f},{y + h - ry:.1f} A{w / 2:.1f},{ry} 0 0 1 {x:.1f},{y + h - ry:.1f} Z"
        )
        self.add(
            f'<path d="{body}" fill="{fill}" stroke="{stroke}" stroke-width="1.4" filter="url(#shadow)"/>'
        )
        self.add(
            f'<path d="M{x:.1f},{y + ry:.1f} A{w / 2:.1f},{ry} 0 0 0 {x + w:.1f},{y + ry:.1f}" '
            f'fill="none" stroke="{stroke}" stroke-width="1.4"/>'
        )
        self._box_text(x, y + ry * 1.4, w, h - ry * 1.4, title, tech, lines, stroke=stroke, badge=None,
                       align=align, title_size=title_size, line_size=line_size, mono_lines=False,
                       icon=None, pad=14, top=y + ry * 1.4, title_color=INK)  # fmt: skip
        return Box(x, y, w, h)

    def group(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        label: str,
        *,
        color: str = MUTED,
        fill: str = PANEL,
    ) -> Box:
        self.rect(x, y, w, h, fill=fill, stroke=FAINT, dashed=True, rx=14, sw=1.2)
        self.text(
            x + 16, y + 22, label.upper(), size=11, bold=True, color=color, spacing=1.1, maxw=w - 32
        )
        return Box(x, y, w, h)

    def chip(self, x: float, y: float, value: str, *, fill: str = WHITE, stroke: str = RULE, color: str = INK,
             mono: bool = True, size: float = 10.5, h: float = 20) -> float:  # fmt: skip
        w = text_width(value, size, mono=mono) + 14
        self.rect(x, y, w, h, fill=fill, stroke=stroke, rx=h / 2, sw=1)
        self.text(x + 7, y + h / 2 + size * 0.36, value, size=size, mono=mono, color=color)
        return w

    def pill(self, x: float, y: float, value: str, kind: str) -> float:
        fill, stroke = KINDS[kind]
        return self.chip(x, y, value, fill=fill, stroke=stroke, color=stroke if kind != "note" else MUTED,
                         mono=False, size=11, h=22)  # fmt: skip

    # ---- connectors --------------------------------------------------------------------------
    def _marker(self, color: str) -> str:
        key = color.lstrip("#")
        self.markers.add(color)
        return f"url(#arr-{key})"

    def arrow(
        self,
        points: list[tuple[float, float]],
        label: str | None = None,
        *,
        at: tuple[float, float] | None = None,
        color: str = MUTED,
        dashed: bool = False,
        both: bool = False,
        head: bool = True,
        sw: float = 1.5,
        size: float = 11.5,
        bg: bool = True,
        anchor: str = "middle",
        label_color: str | None = None,
        start_marker: str | None = None,
        end_marker: str | None = None,
    ) -> None:
        dash = ' stroke-dasharray="6 4"' if dashed else ""
        ends = ""
        if end_marker:
            ends += f' marker-end="url(#{end_marker})"'
        elif head:
            ends += f' marker-end="{self._marker(color)}"'
        if start_marker:
            ends += f' marker-start="url(#{start_marker})"'
        elif both:
            ends += f' marker-start="{self._marker(color)}"'
        self.add(
            f'<path d="{_rounded_path(points)}" fill="none" stroke="{color}" stroke-width="{sw}"{dash}{ends}/>'
        )
        if label:
            if at is None:
                best = max(
                    range(len(points) - 1), key=lambda i: math.dist(points[i], points[i + 1])
                )
                (x0, y0), (x1, y1) = points[best], points[best + 1]
                at = ((x0 + x1) / 2, (y0 + y1) / 2)
            self.label(
                at[0], at[1], label, size=size, bg=bg, anchor=anchor, color=label_color or INK
            )

    def label(self, x: float, y: float, value: str, *, size: float = 11.5, bg: bool = True, anchor: str = "middle",
              color: str = INK, bold: bool = False) -> None:  # fmt: skip
        rows = value.split("\n")
        widths = [text_width(r, size, bold=bold) for r in rows]
        lh = size * 1.3
        height = lh * len(rows) + 4
        width = max(widths) + 10
        left = (
            x - width / 2 if anchor == "middle" else (x - 5 if anchor == "start" else x - width + 5)
        )
        top = y - height / 2
        if bg:
            self.add(
                f'<rect x="{left:.1f}" y="{top:.1f}" width="{width:.1f}" height="{height:.1f}" rx="4" '
                f'fill="{WHITE}" fill-opacity="0.94"/>'
            )
        for i, row in enumerate(rows):
            self.text(
                x, top + 2 + lh * (i + 0.78), row, size=size, color=color, anchor=anchor, bold=bold
            )

    # ---- legend and frame --------------------------------------------------------------------
    def legend(self, x: float, y: float, kinds: list, *, extra: list[tuple[str, str]] = ()) -> None:
        cursor = x
        for item in kinds:
            kind, name = item if isinstance(item, tuple) else (item, KIND_NAMES[item])
            fill, stroke = KINDS[kind]
            dash = ' stroke-dasharray="4 3"' if kind == "external" else ""
            self.add(
                f'<rect x="{cursor:.1f}" y="{y - 10:.1f}" width="18" height="13" rx="3" fill="{fill}" '
                f'stroke="{stroke}" stroke-width="1.3"{dash}/>'
            )
            cursor += 24
            cursor += self.text(cursor, y, name, size=11.5, color=MUTED) + 18
        for style, name in extra:
            dash = ' stroke-dasharray="6 4"' if style == "dashed" else ""
            self.add(
                f'<line x1="{cursor:.1f}" y1="{y - 4:.1f}" x2="{cursor + 26:.1f}" y2="{y - 4:.1f}" '
                f'stroke="{MUTED}" stroke-width="1.5"{dash} marker-end="{self._marker(MUTED)}"/>'
            )
            cursor += 34
            cursor += self.text(cursor, y, name, size=11.5, color=MUTED) + 18

    def frame(self, x: float, y: float, w: float, h: float, label: str) -> None:
        """A UML-style frame (loop, alt) for sequence diagrams."""
        self.rect(x, y, w, h, fill="none", stroke=FAINT, rx=6, sw=1.2)
        tw = text_width(label, 11, bold=True) + 18
        self.add(
            f'<path d="M{x:.1f},{y + 20:.1f} L{x + tw - 8:.1f},{y + 20:.1f} L{x + tw:.1f},{y + 12:.1f} '
            f'L{x + tw:.1f},{y:.1f}" fill="{PANEL}" stroke="{FAINT}" stroke-width="1.2"/>'
        )
        self.text(x + 8, y + 14.5, label, size=11, bold=True, color=MUTED)

    # ---- output ------------------------------------------------------------------------------
    def svg(self) -> str:
        defs = [
            '<filter id="shadow" x="-5%" y="-5%" width="110%" height="120%">'
            '<feDropShadow dx="0" dy="1.2" stdDeviation="1.6" flood-color="#1C1917" flood-opacity="0.09"/>'
            "</filter>"
        ]
        for color in sorted(self.markers):
            key = color.lstrip("#")
            defs.append(
                f'<marker id="arr-{key}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" '
                f'markerHeight="9" orient="auto-start-reverse" markerUnits="userSpaceOnUse">'
                f'<path d="M0,0.8 L10,5 L0,9.2 Z" fill="{color}"/></marker>'
            )
        # entity-relationship ends: one (two bars), zero-or-one (bar + ring), many (crow's foot)
        defs.append(
            f'<marker id="er-one" viewBox="-16 -9 18 18" refX="0" refY="0" markerWidth="18" markerHeight="18" '
            f'orient="auto-start-reverse" markerUnits="userSpaceOnUse"><path d="M-6,-7 L-6,7 M-11,-7 L-11,7" '
            f'stroke="{MUTED}" stroke-width="1.5" fill="none"/></marker>'
        )
        defs.append(
            f'<marker id="er-zero-one" viewBox="-22 -9 24 18" refX="0" refY="0" markerWidth="24" markerHeight="18" '
            f'orient="auto-start-reverse" markerUnits="userSpaceOnUse"><path d="M-6,-7 L-6,7" stroke="{MUTED}" '
            f'stroke-width="1.5"/><circle cx="-14" cy="0" r="4" fill="{WHITE}" stroke="{MUTED}" stroke-width="1.5"/></marker>'
        )
        defs.append(
            f'<marker id="er-many" viewBox="-16 -9 18 18" refX="0" refY="0" markerWidth="18" markerHeight="18" '
            f'orient="auto" markerUnits="userSpaceOnUse"><path d="M-12,0 L0,-7 M-12,0 L0,0 M-12,0 L0,7 M-14,-7 L-14,7" '
            f'stroke="{MUTED}" stroke-width="1.5" fill="none"/></marker>'
        )
        head = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}" role="img" aria-labelledby="t d">',
            f'<title id="t">{esc(self.title)}</title><desc id="d">{esc(self.subtitle)}</desc>',
            f"<defs>{''.join(defs)}</defs>",
            f'<rect width="{self.w}" height="{self.h}" fill="{WHITE}"/>',
        ]
        chrome = []
        saved, self.body = self.body, []
        self.text(48, 62, self.title, size=28, bold=True)
        self.text(48, 90, self.subtitle, size=15, color=MUTED, maxw=self.w - 96)
        self.text(48, self.h - 24, "AI Podcast Engine · Architecture", size=11, color=MUTED)
        self.text(
            self.w - 48,
            self.h - 24,
            f"{self.number:02d} / {self.total:02d}",
            size=11,
            color=MUTED,
            anchor="end",
        )
        chrome, self.body = self.body, saved
        return "\n".join(head + chrome + self.body + ["</svg>"])

    def save(self, out: Path) -> Path:
        content = self.svg()
        if self.problems:
            raise SystemExit("Text does not fit:\n  " + "\n  ".join(self.problems))
        path = out / f"{self.slug}.svg"
        path.write_text(content, encoding="utf-8")
        return path
