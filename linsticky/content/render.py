"""
Rendering of note segments into Pango markup.

Pure Python (no GTK import) so it can be unit-tested.
"""
import html

_SIMPLE_TAGS = {
    "bold": ("<b>", "</b>"),
    "italic": ("<i>", "</i>"),
    "underline": ("<u>", "</u>"),
    "strikethrough": ("<s>", "</s>"),
}


def _tag_markup(tag: str):
    """Returns (opening, closing) markup for a buffer tag name, or None."""
    if tag in _SIMPLE_TAGS:
        return _SIMPLE_TAGS[tag]
    if tag.startswith("text_color_"):
        color = html.escape(tag[len("text_color_"):], quote=True)
        return f'<span foreground="{color}">', "</span>"
    if tag.startswith("font_size_"):
        size = tag[len("font_size_"):]
        if size.isdigit():
            return f'<span size="{size}pt">', "</span>"
    return None


def segments_to_pango(segments: list[dict], max_lines=None) -> str:
    """
    Generates Pango markup from a list of text segments and their tags.

    Args:
        segments: List of {"text": str, "tags": [str]} dictionaries.
        max_lines: If given, output is cut after this many lines
                   (used for the main window preview cards).
    """
    if not segments:
        return ""

    parts = []
    line_count = 0

    for seg in segments:
        text = seg.get("text", "")
        if max_lines is not None:
            lines_in_seg = text.split("\n")
            if line_count >= max_lines:
                break
            if line_count + len(lines_in_seg) - 1 >= max_lines:
                allowed = max_lines - line_count
                text = "\n".join(lines_in_seg[:allowed])
                line_count = max_lines
            else:
                line_count += len(lines_in_seg) - 1

        opening, closing = [], []
        for tag in seg.get("tags", []):
            markup = _tag_markup(tag)
            if markup:
                opening.append(markup[0])
                closing.insert(0, markup[1])

        parts.append("".join(opening) + html.escape(text) + "".join(closing))

    return "".join(parts).rstrip()
