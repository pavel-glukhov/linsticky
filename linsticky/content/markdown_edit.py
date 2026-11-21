"""
Markdown toolbar: button registry and text-editing operations.

Pure Python (no GTK) so the editing logic can be unit-tested. Every operation
takes the full note text plus the selection (character offsets) and returns an
:class:`Edit` describing which range to replace and what to select afterwards.
"""
import re
from dataclasses import dataclass


def N_(message: str) -> str:
    """Marks a string for translation without translating it (see tools/i18n.py)."""
    return message


@dataclass(frozen=True)
class ToolbarButton:
    key: str            # config key and action id
    label: str          # Pango markup shown on the button (unless icon is set)
    icon: str           # symbolic icon name, or "" to use the label
    tooltip: str        # tooltip, marked with N_() and translated by the UI
    default: bool       # shown by default


# Order = order on the sticker toolbar and in the settings.
MD_TOOLBAR = (
    ToolbarButton("bold", "<b>B</b>", "", N_("Bold"), True),
    ToolbarButton("italic", "<i>I</i>", "", N_("Italic"), True),
    ToolbarButton("strikethrough", "<s>S</s>", "", N_("Strikethrough"), True),
    ToolbarButton("heading", "<b>H</b>", "", N_("Heading"), True),
    ToolbarButton("code", "<tt>&lt;&gt;</tt>", "", N_("Inline code"), True),
    ToolbarButton("link", "", "insert-link-symbolic", N_("Link"), True),
    ToolbarButton("list", "≡", "", N_("Bullet List"), True),
    ToolbarButton("ordered_list", "1.", "", N_("Numbered list"), False),
    ToolbarButton("task_list", "☑", "", N_("Task list"), True),
    ToolbarButton("quote", "<b>”</b>", "", N_("Quote"), False),
    ToolbarButton("code_block", "<tt>{ }</tt>", "", N_("Code block"), False),
    ToolbarButton("hr", "—", "", N_("Horizontal rule"), False),
)

MD_TOOLBAR_DEFAULTS = {b.key: b.default for b in MD_TOOLBAR}


@dataclass(frozen=True)
class Edit:
    start: int          # replace text[start:end] ...
    end: int
    text: str           # ... with this
    sel_start: int      # selection afterwards (offsets in the new text)
    sel_end: int


WRAP_MARKERS = {"bold": "**", "italic": "*", "strikethrough": "~~", "code": "`"}

_LIST_MARKER_RE = re.compile(r"^(\s*)(?:[-*+] \[[ xX]\] |[-*+] |\d+[.)] )")
_QUOTE_RE = re.compile(r"^(\s*)> ?")
_HEADING_RE = re.compile(r"^(#{1,6}) +")
_URL_RE = re.compile(r"^(https?://|www\.)\S+$", re.IGNORECASE)


def apply(action: str, text: str, sel_start: int, sel_end: int):
    """Runs toolbar action ``action``; returns an :class:`Edit` or None."""
    s, e = sorted((max(0, sel_start), min(len(text), sel_end)))
    if action in WRAP_MARKERS:
        return wrap(text, s, e, WRAP_MARKERS[action])
    if action in ("list", "ordered_list", "task_list"):
        return toggle_list(text, s, e, action)
    if action == "quote":
        return toggle_quote(text, s, e)
    if action == "heading":
        return cycle_heading(text, s, e)
    if action == "link":
        return insert_link(text, s, e)
    if action == "code_block":
        return code_block(text, s, e)
    if action == "hr":
        return horizontal_rule(text, s, e)
    return None


# ---------------------------------------------------------------- inline
def wrap(text: str, s: int, e: int, marker: str) -> Edit:
    """Toggles ``marker`` around the selection (or inserts an empty pair)."""
    n = len(marker)
    if s == e:
        return Edit(s, s, marker + marker, s + n, s + n)

    selected = text[s:e]
    if len(selected) >= 2 * n and selected.startswith(marker) and selected.endswith(marker):
        inner = selected[n:-n]
        return Edit(s, e, inner, s, s + len(inner))
    if text[max(0, s - n):s] == marker and text[e:e + n] == marker and s >= n:
        return Edit(s - n, e + n, selected, s - n, s - n + len(selected))
    return Edit(s, e, marker + selected + marker, s + n, s + n + len(selected))


def insert_link(text: str, s: int, e: int) -> Edit:
    selected = text[s:e]
    if selected and _URL_RE.match(selected.strip()):
        new = f"[]({selected.strip()})"
        return Edit(s, e, new, s + 1, s + 1)
    label = selected or "text"
    new = f"[{label}](https://)"
    if selected:
        url_at = s + len(label) + 3
        return Edit(s, e, new, url_at, url_at + len("https://"))
    return Edit(s, e, new, s + 1, s + 1 + len(label))


# ---------------------------------------------------------------- blocks
def _line_range(text: str, s: int, e: int):
    start = text.rfind("\n", 0, s) + 1
    # A selection ending right after a newline does not include the next line.
    probe = e - 1 if e > s and text[e - 1] == "\n" else e
    end = text.find("\n", probe)
    return start, (len(text) if end == -1 else end)


def _replace_lines(text, s, e, transform) -> Edit:
    """Applies ``transform(lines) -> lines`` to the lines covered by [s, e]."""
    ls, le = _line_range(text, s, e)
    old = text[ls:le]
    lines = old.split("\n")
    new_lines = transform(lines)
    new = "\n".join(new_lines)
    if s == e and len(lines) == 1:
        # Keep the caret at the same place in the line content.
        delta = len(new_lines[0]) - len(lines[0])
        caret = max(ls, min(ls + len(new), s + delta))
        return Edit(ls, le, new, caret, caret)
    return Edit(ls, le, new, ls, ls + len(new))


def _list_marker(kind: str, index: int) -> str:
    return {"list": "- ", "task_list": "- [ ] ", "ordered_list": f"{index}. "}[kind]


def _has_marker(line: str, kind: str) -> bool:
    m = _LIST_MARKER_RE.match(line)
    if not m:
        return False
    marker = m.group(0)[len(m.group(1)):]
    if kind == "task_list":
        return marker[2:3] == "["
    if kind == "ordered_list":
        return marker[0].isdigit()
    return marker[0] in "-*+" and marker[2:3] != "["


def toggle_list(text: str, s: int, e: int, kind: str) -> Edit:
    def transform(lines):
        multi = len(lines) > 1
        targets = [i for i, l in enumerate(lines) if l.strip() or not multi]
        remove = targets and all(_has_marker(lines[i], kind) for i in targets)
        out = list(lines)
        number = 1
        for i in targets:
            line = lines[i]
            m = _LIST_MARKER_RE.match(line)
            indent, body = (m.group(1), line[m.end():]) if m else ("", line)
            if not m:
                body = line.lstrip()
                indent = line[:len(line) - len(body)]
            if remove:
                out[i] = indent + body
            else:
                out[i] = indent + _list_marker(kind, number) + body
                number += 1
        return out
    return _replace_lines(text, s, e, transform)


def toggle_quote(text: str, s: int, e: int) -> Edit:
    def transform(lines):
        multi = len(lines) > 1
        targets = [i for i, l in enumerate(lines) if l.strip() or not multi]
        remove = targets and all(_QUOTE_RE.match(lines[i]) for i in targets)
        out = list(lines)
        for i in targets:
            if remove:
                out[i] = _QUOTE_RE.sub(r"\1", lines[i], count=1)
            else:
                out[i] = "> " + lines[i]
        return out
    return _replace_lines(text, s, e, transform)


def cycle_heading(text: str, s: int, e: int) -> Edit:
    """No heading -> # -> ## -> ### -> no heading (based on the first line)."""
    def transform(lines):
        m = _HEADING_RE.match(lines[0])
        level = len(m.group(1)) if m else 0
        new_level = 0 if level >= 3 else level + 1
        prefix = "#" * new_level + " " if new_level else ""
        return [prefix + _HEADING_RE.sub("", l, count=1) if (l.strip() or len(lines) == 1) else l
                for l in lines]
    return _replace_lines(text, s, e, transform)


def code_block(text: str, s: int, e: int) -> Edit:
    selected = text[s:e]
    before = "" if s == 0 or text[s - 1] == "\n" else "\n"
    after = "" if e == len(text) or text[e] == "\n" else "\n"
    body = selected.rstrip("\n")
    new = f"{before}```\n{body}\n```{after}"
    inner = s + len(before) + 4
    return Edit(s, e, new, inner, inner + len(body))


def horizontal_rule(text: str, s: int, e: int) -> Edit:
    before = "" if s == 0 or text[s - 1] == "\n" else "\n"
    new = f"{before}---\n"
    caret = s + len(new)
    return Edit(s, e, new, caret, caret)
