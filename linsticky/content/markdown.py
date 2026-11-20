"""
Minimal Markdown support for notes in "Markdown mode".

A Markdown note stores its raw source as ordinary, untagged text (so older
versions of the app simply show the source). This module renders that source
to Pango markup for the preview, and converts between Markdown and the rich
segment format used by regular notes.

Supported syntax (a pragmatic subset of CommonMark):

* Blocks: ``#``..``######`` headings, ``-``/``*``/``+`` bullet lists,
  ``1.``/``1)`` ordered lists, ``- [ ]``/``- [x]`` task lists, ``>`` quotes,
  ``---``/``***``/``___`` horizontal rules, fenced code blocks (``````` or ``~~~``).
* Inline: ``**bold**``/``__bold__``, ``*italic*``/``_italic_``,
  ``~~strikethrough~~``, ```code```, ``[text](url)``, ``<url>`` and bare
  ``http(s)://`` links, backslash escapes.

Pure Python (no GTK import) so it can be unit-tested.
"""
import html
import re
from dataclasses import dataclass, field

# --------------------------------------------------------------------------- inline

BOLD, ITALIC, STRIKE, CODE, LINK = "bold", "italic", "strike", "code", "link"

_ESCAPABLE = set("\\`*_~[]()#+-.!>|{}")
_CODE_RE = re.compile(r"(`+)(.+?)\1")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_AUTOLINK_RE = re.compile(r"<(https?://[^>\s]+)>", re.IGNORECASE)
_URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
_BOLD_ITALIC_RE = {"*": re.compile(r"\*\*\*(?=\S)(.+?)(?<=\S)\*\*\*"),
                   "_": re.compile(r"___(?=\S)(.+?)(?<=\S)___")}
_BOLD_RE = {"*": re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*"),
            "_": re.compile(r"__(?=\S)(.+?)(?<=\S)__")}
_ITALIC_RE = {"*": re.compile(r"\*(?=[^\s*])(.+?)(?<=[^\s*])\*"),
              "_": re.compile(r"_(?=[^\s_])(.+?)(?<=[^\s_])_")}
_STRIKE_RE = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~")
_URL_TRAILING = ".,;:!?)]}'\""


@dataclass(frozen=True)
class Run:
    """A piece of inline text with a set of styles and an optional link target."""
    text: str
    styles: frozenset = frozenset()
    href: str = None


def _word_char(ch: str) -> bool:
    return ch.isalnum()


def _underscore_boundary_ok(text: str, start: int, end: int) -> bool:
    """``_`` emphasis must not start or end inside a word (snake_case stays literal)."""
    before = text[start - 1] if start > 0 else " "
    after = text[end] if end < len(text) else " "
    return not _word_char(before) and not _word_char(after)


def parse_inline(text: str, styles: frozenset = frozenset(), href: str = None) -> list[Run]:
    """Parses inline Markdown into a list of Runs."""
    runs: list[Run] = []
    buf: list[str] = []
    i, n = 0, len(text)

    def flush():
        if buf:
            runs.append(Run("".join(buf), styles, href))
            buf.clear()

    while i < n:
        c = text[i]

        if c == "\\" and i + 1 < n and text[i + 1] in _ESCAPABLE:
            buf.append(text[i + 1])
            i += 2
            continue

        if c == "`":
            m = _CODE_RE.match(text, i)
            if m:
                flush()
                runs.append(Run(m.group(2), styles | {CODE}, href))
                i = m.end()
                continue

        if href is None:
            if c == "[":
                m = _LINK_RE.match(text, i)
                if m:
                    flush()
                    runs.extend(parse_inline(m.group(1), styles | {LINK}, m.group(2)))
                    i = m.end()
                    continue
            elif c == "<":
                m = _AUTOLINK_RE.match(text, i)
                if m:
                    flush()
                    runs.append(Run(m.group(1), styles | {LINK}, m.group(1)))
                    i = m.end()
                    continue
            elif c in "hH" and (i == 0 or not _word_char(text[i - 1])):
                m = _URL_RE.match(text, i)
                if m:
                    url = m.group(0).rstrip(_URL_TRAILING)
                    if len(url) > len("https://"):
                        flush()
                        runs.append(Run(url, styles | {LINK}, url))
                        i += len(url)
                        continue

        if c in "*_":
            if text.startswith(c * 3, i):
                m = _BOLD_ITALIC_RE[c].match(text, i)
                if m and (c == "*" or _underscore_boundary_ok(text, i, m.end())):
                    flush()
                    runs.extend(parse_inline(m.group(1), styles | {BOLD, ITALIC}, href))
                    i = m.end()
                    continue
            if text.startswith(c * 2, i):
                m = _BOLD_RE[c].match(text, i)
                if m and (c == "*" or _underscore_boundary_ok(text, i, m.end())):
                    flush()
                    runs.extend(parse_inline(m.group(1), styles | {BOLD}, href))
                    i = m.end()
                    continue
            m = _ITALIC_RE[c].match(text, i)
            if m and (c == "*" or _underscore_boundary_ok(text, i, m.end())):
                flush()
                runs.extend(parse_inline(m.group(1), styles | {ITALIC}, href))
                i = m.end()
                continue

        if c == "~" and text.startswith("~~", i):
            m = _STRIKE_RE.match(text, i)
            if m:
                flush()
                runs.extend(parse_inline(m.group(1), styles | {STRIKE}, href))
                i = m.end()
                continue

        buf.append(c)
        i += 1

    flush()
    return _merge_runs(runs)


def _merge_runs(runs: list[Run]) -> list[Run]:
    merged: list[Run] = []
    for run in runs:
        if not run.text:
            continue
        if merged and merged[-1].styles == run.styles and merged[-1].href == run.href:
            merged[-1] = Run(merged[-1].text + run.text, run.styles, run.href)
        else:
            merged.append(run)
    return merged


# --------------------------------------------------------------------------- blocks

_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)(?:\s+#+)?\s*$")
_HR_RE = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
_TASK_RE = re.compile(r"^(\s*)[-*+]\s+\[([ xX])\]\s+(.*)$")
_BULLET_RE = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_ORDERED_RE = re.compile(r"^(\s*)(\d{1,9})([.)])\s+(.*)$")
_QUOTE_RE = re.compile(r"^\s{0,3}>\s?(.*)$")
_FENCE_RE = re.compile(r"^\s{0,3}(```|~~~)")


@dataclass
class Block:
    """One rendered line of a Markdown document."""
    kind: str                 # blank, para, heading, bullet, ordered, task, quote, hr, code
    text: str = ""            # inline source (or verbatim text for code)
    level: int = 0            # heading level or list nesting depth
    marker: str = ""          # ordered list marker, e.g. "1."
    checked: bool = False     # task state
    runs: list = field(default_factory=list)


def _depth(indent: str) -> int:
    return len(indent.expandtabs(4)) // 2


def parse_blocks(source: str) -> list[Block]:
    """Splits Markdown source into line-level blocks."""
    blocks: list[Block] = []
    fence = None
    for line in source.split("\n"):
        fence_match = _FENCE_RE.match(line)
        if fence is not None:
            if fence_match and fence_match.group(1) == fence:
                fence = None
            else:
                blocks.append(Block("code", line))
            continue
        if fence_match:
            fence = fence_match.group(1)
            continue

        if not line.strip():
            blocks.append(Block("blank"))
        elif m := _HEADING_RE.match(line):
            blocks.append(Block("heading", m.group(2), level=len(m.group(1))))
        elif _HR_RE.match(line):
            blocks.append(Block("hr"))
        elif m := _TASK_RE.match(line):
            blocks.append(Block("task", m.group(3), level=_depth(m.group(1)),
                                checked=m.group(2) in "xX"))
        elif m := _BULLET_RE.match(line):
            blocks.append(Block("bullet", m.group(2), level=_depth(m.group(1))))
        elif m := _ORDERED_RE.match(line):
            blocks.append(Block("ordered", m.group(4), level=_depth(m.group(1)),
                                marker=m.group(2) + m.group(3)))
        elif m := _QUOTE_RE.match(line):
            blocks.append(Block("quote", m.group(1)))
        else:
            blocks.append(Block("para", line))

    for block in blocks:
        if block.kind not in ("code", "blank", "hr"):
            block.runs = parse_inline(block.text)
    return blocks


# --------------------------------------------------------------------------- Pango

_HEADING_SIZES = {1: "xx-large", 2: "x-large", 3: "large"}
_BULLETS = ("•", "◦", "▪")
_CODE_SPAN = '<span font_family="monospace" background="#000000" bgalpha="8%">'
_MUTED = "#555555"


def _runs_to_pango(runs: list[Run], links: bool) -> str:
    out = []
    for run in runs:
        text = html.escape(run.text, quote=False)
        if CODE in run.styles:
            text = f"{_CODE_SPAN}{text}</span>"
        if STRIKE in run.styles:
            text = f"<s>{text}</s>"
        if ITALIC in run.styles:
            text = f"<i>{text}</i>"
        if BOLD in run.styles:
            text = f"<b>{text}</b>"
        if run.href:
            if links:
                text = f'<a href="{html.escape(run.href, quote=True)}">{text}</a>'
            else:
                text = f'<span foreground="#1565C0" underline="single">{text}</span>'
        out.append(text)
    return "".join(out)


def _indent(level: int) -> str:
    return "    " * level


def _block_to_pango(block: Block, links: bool) -> str:
    inline = _runs_to_pango(block.runs, links)
    kind = block.kind
    if kind == "blank":
        return ""
    if kind == "heading":
        size = _HEADING_SIZES.get(block.level)
        if size:
            return f'<span size="{size}" weight="bold">{inline}</span>'
        return f"<b>{inline}</b>"
    if kind == "bullet":
        return f"{_indent(block.level)}{_BULLETS[block.level % len(_BULLETS)]} {inline}"
    if kind == "ordered":
        return f"{_indent(block.level)}{html.escape(block.marker)} {inline}"
    if kind == "task":
        if block.checked:
            return f'{_indent(block.level)}☑ <span foreground="{_MUTED}"><s>{inline}</s></span>'
        return f"{_indent(block.level)}☐ {inline}"
    if kind == "quote":
        return f'<span foreground="{_MUTED}">▎ <i>{inline}</i></span>'
    if kind == "hr":
        return f'<span foreground="{_MUTED}">{"─" * 24}</span>'
    if kind == "code":
        return f"{_CODE_SPAN}{html.escape(block.text, quote=False) or ' '}</span>"
    return inline


def to_pango(source: str, max_lines: int = None, links: bool = True) -> str:
    """
    Renders Markdown source to Pango markup.

    Args:
        source: Markdown text.
        max_lines: Optional limit of rendered lines (for preview cards).
        links: Emit clickable ``<a>`` links (Gtk.Label); otherwise links are
               only styled, which is what non-interactive previews need.
    """
    blocks = parse_blocks(source or "")
    if max_lines is not None:
        blocks = blocks[:max_lines]
    return "\n".join(_block_to_pango(b, links) for b in blocks).rstrip()


def to_plain(source: str) -> str:
    """Rendered text without any markup (used for search)."""
    lines = []
    for block in parse_blocks(source or ""):
        text = "".join(run.text for run in block.runs) if block.runs else block.text
        lines.append(text)
    return "\n".join(lines)


# --------------------------------------------------------------------------- conversions

RICH_BULLET = " • "
_RICH_TO_MD_MARKERS = (("bold", "**"), ("italic", "*"), ("strikethrough", "~~"))
_MD_STYLE_TO_TAG = {BOLD: "bold", ITALIC: "italic", STRIKE: "strikethrough"}


def rich_is_lossless(segments: list[dict]) -> bool:
    """True if every tag used by the rich note has a Markdown equivalent."""
    supported = {tag for tag, _ in _RICH_TO_MD_MARKERS}
    return all(tag in supported for seg in segments for tag in seg.get("tags", []))


def rich_to_markdown(segments: list[dict]) -> str:
    """
    Converts rich segments to Markdown source. Bold, italic and strikethrough
    become Markdown markers, " • " bullets become "- " items; other formatting
    (underline, colors, font sizes) has no Markdown equivalent and is dropped.
    """
    out = []
    for seg in segments:
        tags = seg.get("tags", [])
        markers = [marker for tag, marker in _RICH_TO_MD_MARKERS if tag in tags]
        opening, closing = "".join(markers), "".join(reversed(markers))
        for k, piece in enumerate(seg.get("text", "").split("\n")):
            if k:
                out.append("\n")
            core = piece.strip()
            if markers and core:
                lead = piece[:len(piece) - len(piece.lstrip())]
                trail = piece[len(piece.rstrip()):]
                out.append(f"{lead}{opening}{core}{closing}{trail}")
            else:
                out.append(piece)
    lines = "".join(out).split("\n")
    return "\n".join("- " + line[len(RICH_BULLET):] if line.startswith(RICH_BULLET) else line
                     for line in lines)


def markdown_to_rich(source: str) -> list[dict]:
    """
    Converts Markdown source to rich segments, keeping bold, italic and
    strikethrough; headings become bold, bullets become " • " items.
    """
    segments: list[dict] = []

    def add(text: str, tags=()):
        if not text:
            return
        tags = sorted(set(tags))
        if segments and segments[-1]["tags"] == tags:
            segments[-1]["text"] += text
        else:
            segments.append({"text": text, "tags": tags})

    blocks = parse_blocks(source or "")
    for index, block in enumerate(blocks):
        if index:
            add("\n")
        extra = []
        kind = block.kind
        if kind == "heading":
            extra = ["bold"]
        elif kind == "bullet":
            add("  " * block.level + RICH_BULLET)
        elif kind == "ordered":
            add("  " * block.level + block.marker + " ")
        elif kind == "task":
            add("  " * block.level + ("☑ " if block.checked else "☐ "))
        elif kind == "quote":
            add("│ ")
            extra = ["italic"]
        elif kind == "hr":
            add("—" * 12)
        elif kind == "code":
            add(block.text)

        for run in block.runs:
            tags = extra + [_MD_STYLE_TO_TAG[s] for s in run.styles if s in _MD_STYLE_TO_TAG]
            text = run.text
            if run.href and run.href != run.text:
                text = f"{text} ({run.href})"
            add(text, tags)

    return segments or [{"text": "", "tags": []}]
