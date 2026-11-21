import json

from content import codec, render


SEGMENTS = [
    {"text": "Hello ", "tags": []},
    {"text": "bold", "tags": ["bold"]},
    {"text": " & <red>\n", "tags": ["text_color_#D32F2F", "font_size_14"]},
]


# ---------------------------------------------------------------- codec
def test_roundtrip_hex_json():
    assert codec.decode(codec.encode(SEGMENTS)) == SEGMENTS


def test_encode_is_backward_compatible_format():
    raw = codec.encode(SEGMENTS)
    assert json.loads(bytes.fromhex(raw).decode("utf-8")) == SEGMENTS


def test_decode_plain_json():
    assert codec.decode(json.dumps(SEGMENTS)) == SEGMENTS


def test_decode_legacy_text_with_br():
    assert codec.decode("line1<br>line2") == [{"text": "line1\nline2", "tags": []}]


def test_decode_empty():
    assert codec.decode(None) == [{"text": "", "tags": []}]
    assert codec.decode("") == [{"text": "", "tags": []}]


def test_decode_hex_looking_plain_text_is_kept():
    # "31" is valid hex for "1", which is valid JSON but not a segment list.
    assert codec.decode("31") == [{"text": "31", "tags": []}]
    assert codec.decode("cafe") == [{"text": "cafe", "tags": []}]


def test_decode_drops_garbage_fields():
    raw = json.dumps([{"text": "a", "tags": ["bold", 5]}, {"tags": None}])
    assert codec.decode(raw) == [{"text": "a", "tags": ["bold"]}, {"text": "", "tags": []}]


def test_plain_text():
    assert codec.plain_text(SEGMENTS) == "Hello bold & <red>\n"


# ---------------------------------------------------------------- render
def _legacy_generate_markup(segments):
    """Verbatim copy of the pre-refactoring NoteCard._generate_markup."""
    import html as html_lib
    if not segments: return ""
    full_markup = ""
    line_count = 0
    for seg in segments:
        text = seg.get("text", "")
        lines_in_seg = text.split('\n')
        if line_count >= 5:
            break
        if line_count + len(lines_in_seg) - 1 >= 5:
            allowed = 5 - line_count
            text = "\n".join(lines_in_seg[:allowed])
            line_count = 5
        else:
            line_count += len(lines_in_seg) - 1
        safe_text = html_lib.escape(text)
        opening_tags = []
        closing_tags = []
        for tag in seg.get("tags", []):
            if tag == "bold":
                opening_tags.append("<b>"); closing_tags.insert(0, "</b>")
            elif tag == "italic":
                opening_tags.append("<i>"); closing_tags.insert(0, "</i>")
            elif tag == "underline":
                opening_tags.append("<u>"); closing_tags.insert(0, "</u>")
            elif tag == "strikethrough":
                opening_tags.append("<s>"); closing_tags.insert(0, "</s>")
            elif tag.startswith("text_color_"):
                c = tag.replace("text_color_", "")
                opening_tags.append(f'<span foreground="{c}">'); closing_tags.insert(0, "</span>")
            elif tag.startswith("font_size_"):
                s = tag.replace("font_size_", "")
                opening_tags.append(f'<span size="{s}pt">'); closing_tags.insert(0, "</span>")
        full_markup += "".join(opening_tags) + safe_text + "".join(closing_tags)
    return full_markup.rstrip()


def test_render_matches_legacy_preview():
    cases = [
        SEGMENTS,
        [{"text": "a\nb\nc\nd\ne\nf\ng", "tags": ["italic"]}],
        [{"text": "1\n2\n", "tags": []}, {"text": "3\n4\n5\n6", "tags": ["underline", "strikethrough"]}],
        [],
    ]
    for segments in cases:
        assert render.segments_to_pango(segments, max_lines=5) == _legacy_generate_markup(segments)


def test_render_without_limit_keeps_all_lines():
    segments = [{"text": "\n".join(str(i) for i in range(10)), "tags": []}]
    assert render.segments_to_pango(segments).count("\n") == 9
