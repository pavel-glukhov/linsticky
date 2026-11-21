from content import markdown as md
from content.markdown import Run, BOLD, ITALIC, STRIKE, CODE, LINK


def styles(*names):
    return frozenset(names)


# ---------------------------------------------------------------- inline
def test_inline_basic_styles():
    assert md.parse_inline("a **b** *c* ~~d~~ `e`") == [
        Run("a "), Run("b", styles(BOLD)), Run(" "), Run("c", styles(ITALIC)),
        Run(" "), Run("d", styles(STRIKE)), Run(" "), Run("e", styles(CODE)),
    ]


def test_inline_nested_bold_italic():
    assert md.parse_inline("***x***") == [Run("x", styles(BOLD, ITALIC))]
    assert md.parse_inline("**a *b* c**") == [
        Run("a ", styles(BOLD)), Run("b", styles(BOLD, ITALIC)), Run(" c", styles(BOLD)),
    ]


def test_inline_underscore_inside_words_is_literal():
    assert md.parse_inline("snake_case_name") == [Run("snake_case_name")]
    assert md.parse_inline("_it_ and __b__") == [
        Run("it", styles(ITALIC)), Run(" and "), Run("b", styles(BOLD)),
    ]


def test_inline_code_is_not_parsed_further():
    assert md.parse_inline("`**x**`") == [Run("**x**", styles(CODE))]


def test_inline_escapes():
    assert md.parse_inline(r"\*not italic\*") == [Run("*not italic*")]


def test_inline_unclosed_markers_stay_literal():
    assert md.parse_inline("2 * 3 = 6 and a*") == [Run("2 * 3 = 6 and a*")]


def test_inline_links():
    assert md.parse_inline("see [docs](https://x.io) or <https://y.io>, https://z.io.") == [
        Run("see "), Run("docs", styles(LINK), "https://x.io"), Run(" or "),
        Run("https://y.io", styles(LINK), "https://y.io"), Run(", "),
        Run("https://z.io", styles(LINK), "https://z.io"), Run("."),
    ]


# ---------------------------------------------------------------- blocks
def test_blocks():
    src = "# Title\n- item\n  - sub\n1. one\n- [x] done\n- [ ] todo\n> quote\n---\n\ntext"
    kinds = [(b.kind, b.level) for b in md.parse_blocks(src)]
    assert kinds == [("heading", 1), ("bullet", 0), ("bullet", 1), ("ordered", 0),
                     ("task", 0), ("task", 0), ("quote", 0), ("hr", 0), ("blank", 0), ("para", 0)]
    blocks = md.parse_blocks(src)
    assert blocks[4].checked and not blocks[5].checked
    assert blocks[3].marker == "1."


def test_code_fence_is_verbatim():
    blocks = md.parse_blocks("```\n# not a heading\n**x**\n```\nafter")
    assert [(b.kind, b.text) for b in blocks] == [
        ("code", "# not a heading"), ("code", "**x**"), ("para", "after"),
    ]


# ---------------------------------------------------------------- pango
def test_pango_escapes_and_formats():
    out = md.to_pango("# A & B\n**<b>**")
    assert out == '<span size="xx-large" weight="bold">A &amp; B</span>\n<b>&lt;b&gt;</b>'


def test_pango_links_toggle():
    assert '<a href="https://x.io">x</a>' in md.to_pango("[x](https://x.io)")
    assert "<a " not in md.to_pango("[x](https://x.io)", links=False)


def test_pango_href_is_attribute_escaped():
    out = md.to_pango('[x](https://a.io/?q="1"&b=2)')
    assert 'href="https://a.io/?q=&quot;1&quot;&amp;b=2"' in out


def test_pango_max_lines():
    assert md.to_pango("1\n2\n3\n4\n5\n6\n7", max_lines=5) == "1\n2\n3\n4\n5"


def test_to_plain():
    assert md.to_plain("# Head\n- **bold** item") == "Head\nbold item"

