from content import markdown_edit as me


def run(action, text, s, e=None):
    e = s if e is None else e
    ed = me.apply(action, text, s, e)
    new = text[:ed.start] + ed.text + text[ed.end:]
    return new, new[ed.sel_start:ed.sel_end], (ed.sel_start, ed.sel_end)


def test_wrap_and_unwrap():
    new, sel, _ = run("bold", "a word b", 2, 6)
    assert new == "a **word** b" and sel == "word"
    # Toggling again with the inner text selected removes the markers.
    new2, sel2, _ = run("bold", new, 4, 8)
    assert new2 == "a word b" and sel2 == "word"
    # Selection that includes the markers.
    new3, _, _ = run("bold", new, 2, 10)
    assert new3 == "a word b"


def test_wrap_empty_selection_places_caret_inside():
    new, _, pos = run("code", "ab", 1)
    assert new == "a``b" and pos == (2, 2)


def test_bullet_list_toggle_multi_line_skips_blank():
    text = "one\n\ntwo"
    new, _, _ = run("list", text, 0, len(text))
    assert new == "- one\n\n- two"
    back, _, _ = run("list", new, 0, len(new))
    assert back == text


def test_list_kinds_replace_each_other():
    new, _, _ = run("task_list", "- a\n- b", 0, 7)
    assert new == "- [ ] a\n- [ ] b"
    new, _, _ = run("ordered_list", new, 0, len(new))
    assert new == "1. a\n2. b"
    new, _, _ = run("list", new, 0, len(new))
    assert new == "- a\n- b"


def test_list_on_caret_keeps_caret_in_content():
    new, _, pos = run("list", "x\nhello", 4)
    assert new == "x\n- hello" and pos == (6, 6)


def test_list_on_empty_line():
    new, _, pos = run("task_list", "", 0)
    assert new == "- [ ] " and pos == (6, 6)


def test_heading_cycles():
    text = "Title"
    seen = []
    for _ in range(4):
        text, _, _ = run("heading", text, 0)
        seen.append(text)
    assert seen == ["# Title", "## Title", "### Title", "Title"]


def test_quote_toggle():
    new, _, _ = run("quote", "a\nb", 0, 3)
    assert new == "> a\n> b"
    back, _, _ = run("quote", new, 0, len(new))
    assert back == "a\nb"


def test_link_variants():
    new, sel, _ = run("link", "see docs", 4, 8)
    assert new == "see [docs](https://)" and sel == "https://"
    new, _, pos = run("link", "https://x.org", 0, 13)
    assert new == "[](https://x.org)" and pos == (1, 1)
    new, sel, _ = run("link", "", 0)
    assert new == "[text](https://)" and sel == "text"


def test_code_block_and_hr():
    new, sel, _ = run("code_block", "a\nprint(1)\nb", 2, 10)
    assert new == "a\n```\nprint(1)\n```\nb" and sel == "print(1)"
    new, _, _ = run("hr", "abc", 3)
    assert new == "abc\n---\n"


def test_selection_ending_after_newline_excludes_next_line():
    new, _, _ = run("list", "a\nb", 0, 2)
    assert new == "- a\nb"


def test_toolbar_defaults_cover_all_buttons():
    assert set(me.MD_TOOLBAR_DEFAULTS) == {b.key for b in me.MD_TOOLBAR}
    assert me.apply("unknown", "x", 0, 0) is None
